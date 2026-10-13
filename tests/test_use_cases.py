from dataclasses import replace
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from app.application.common import Services
from app.application.ports import LimitDecision
from app.application.dto import Principal, DirectoryCommand, PeriodCommand, ScheduleCommand, UserCommand, ProfileCommand, SeriesCommand, MoveCommand, CancelCommand
from app.application.lessons import CreateLesson, MoveLesson, CancelLesson, ListLessons, GetHistory
from app.application.series import CreateSeries, PreviewSeries
from app.application.directories import CreateDirectoryEntry, UpdateDirectoryEntry
from app.application.periods import CreatePeriod
from app.application.schedules import CreateSchedule, PublishSchedule
from app.application.users import CreateUser, ToggleUser
from app.application.auth import Login, Logout, UpdateProfile, ResetGuest, StartGuest
from app.application.maintenance import HealthQuery, CleanupExpiredDemos
from app.domain.values import RequestContext, LessonCommand
from app.domain.errors import DependencyUnavailable, ApplicationError, RateLimited, Forbidden, Unauthorized

CTX = RequestContext(7,3,'admin',False,'test-correlation')
DATA = LessonCommand(1,1,1,1,1,datetime(2026,10,5,6,tzinfo=timezone.utc),datetime(2026,10,5,7,tzinfo=timezone.utc))

def services(decision=None):
    limiter = Mock()
    limiter.consume.return_value = decision or LimitDecision(True)
    uow = Mock()
    uow.__enter__ = Mock(return_value=uow)
    uow.__exit__ = Mock(return_value=False)
    uow.auth.lock_user.return_value={'active':True,'role':'admin'}
    factory = Mock(return_value=uow)
    clock = Mock(); clock.now.return_value=datetime(2026,10,1,tzinfo=timezone.utc)
    tokens = Mock(); tokens.digest.side_effect=lambda x:x
    return Services(factory,limiter,clock,tokens,Mock(),False),uow

@pytest.mark.parametrize('denied',[False,True])
def test_every_mutation_stops_before_uow_when_limiter_fails(denied):
    s,uow=services(LimitDecision(False,12))
    if not denied: s.limiter.consume.side_effect=DependencyUnavailable('redis')
    guest_ctx=replace(CTX,is_guest=True)
    current=Principal(guest_ctx,{}, {'token_hash':'secret'}, {'kind':'demo'})
    calls=[
        lambda:CreateLesson(s).execute(CTX,DATA),
        lambda:MoveLesson(s).execute(CTX,1,MoveCommand(**DATA.__dict__,version=1,reason='move')),
        lambda:CancelLesson(s).execute(CTX,1,CancelCommand('cancel',1)),
        lambda:CreateSeries(s).execute(CTX,SeriesCommand(**DATA.__dict__,until=date(2026,10,12),request_key='request-key')),
        lambda:CreateDirectoryEntry(s).execute(CTX,'groups',DirectoryCommand('new')),
        lambda:UpdateDirectoryEntry(s).execute(CTX,'groups',1,DirectoryCommand('new')),
        lambda:CreatePeriod(s).execute(CTX,PeriodCommand('semester',date(2026,9,1),date(2026,12,1))),
        lambda:CreateSchedule(s).execute(CTX,ScheduleCommand('schedule',1)),
        lambda:PublishSchedule(s).execute(CTX,1),
        lambda:CreateUser(s).execute(CTX,UserCommand('admin2','name','password','admin')),
        lambda:ToggleUser(s).execute(CTX,9),
        lambda:Login(s).execute('name','password','','ip'),
        lambda:UpdateProfile(s).execute(current,ProfileCommand('admin')),
        lambda:ResetGuest(s).execute(current,'ip'),
        lambda:Logout(s).execute(current),
        lambda:CleanupExpiredDemos(s).execute(),
    ]
    for call in calls:
        with pytest.raises(ApplicationError) as error: call()
        assert isinstance(error.value, RateLimited if denied else DependencyUnavailable)
        if denied: assert error.value.retry_after_seconds == 12
        s.uow.assert_not_called()

def test_create_lesson_owns_commit_and_audit_same_transaction():
    s,uow=services()
    uow.schedules.get_schedule.return_value={'period_id':1}
    uow.catalog.get_period.return_value={'start':date(2026,9,1),'end':date(2026,12,1)}
    uow.catalog.get_directory.side_effect=[{'active':True,'name':'G','size':20},{'active':True,'name':'T'},{'active':True,'name':'R','capacity':30},{'active':True,'name':'S'}]
    uow.schedules.conflicts.return_value=[]
    stored=DATA.__dict__ | {'id':17,'series_id':None,'status':'planned','reason':'','version':1}
    uow.schedules.insert_lesson.return_value=stored
    result=CreateLesson(s).execute(CTX,DATA)
    assert result['id']==17
    uow.schedules.append_audit.assert_called_once_with(CTX,'created',stored)
    uow.commit.assert_called_once()
    uow.lock_workspace.assert_called_once_with(7)
    assert s.limiter.consume.call_args.args[1][0].subject != 'write:7'

def test_preview_and_health_do_not_call_limiter_or_commit():
    s,uow=services(); s.limiter.consume.side_effect=AssertionError('read path used Redis')
    assert HealthQuery(s).execute()=={'status':'ok'}
    uow.commit.assert_not_called(); uow.lock_workspace.assert_not_called()

def test_existing_guest_returns_without_write_even_when_redis_is_down():
    s,uow=services(); s.guest_mode=True
    expires=datetime(2026,11,1,tzinfo=timezone.utc)
    user={'id':3,'workspace_id':7,'is_guest':True,'active':True,'role':'student','name':'Guest','group_id':1,'teacher_id':None}
    uow.auth.session_identity.return_value=(user,{'csrf':'csrf','expires':expires},{'kind':'demo','expires':expires})
    s.limiter.consume.side_effect=DependencyUnavailable('redis')
    result=StartGuest(s).execute('admin','token','ip')
    assert result.body['created'] is False and result.raw_token is None
    s.limiter.consume.assert_not_called(); uow.commit.assert_not_called()

def test_new_guest_limiter_failure_never_seeds():
    s,uow=services(); s.guest_mode=True
    uow.auth.session_identity.return_value=None
    s.limiter.consume.side_effect=DependencyUnavailable('redis')
    with pytest.raises(DependencyUnavailable): StartGuest(s).execute('student','','ip')
    uow.demo.seed_workspace.assert_not_called(); uow.demo.reserve_capacity.assert_not_called(); uow.commit.assert_not_called()

def test_role_is_rechecked_after_waiting_for_workspace_lock():
    s,uow=services()
    uow.auth.lock_user.return_value={'active':True,'role':'student'}
    with pytest.raises(ApplicationError) as error: CreateLesson(s).execute(CTX,DATA)
    assert isinstance(error.value,Forbidden)
    uow.schedules.insert_lesson.assert_not_called(); uow.commit.assert_not_called()

def test_disabled_account_cannot_write_after_waiting_for_lock():
    s,uow=services()
    uow.auth.lock_user.return_value={'active':False,'role':'admin'}
    with pytest.raises(ApplicationError) as error: CreatePeriod(s).execute(CTX,PeriodCommand('semester',date(2026,9,1),date(2026,12,1)))
    assert isinstance(error.value,Unauthorized)
    uow.catalog.create_period.assert_not_called(); uow.commit.assert_not_called()
