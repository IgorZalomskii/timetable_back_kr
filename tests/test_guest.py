from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func, text, update, delete
from sqlalchemy.orm import sessionmaker
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from test_api import database, engine, app
from app.models import Workspace, User, Session, Group, Lesson, Schedule, Audit, LoginAttempt
from app.services import MOSCOW
from app.security import token_hash

Factory=sessionmaker(engine,expire_on_commit=False)

def test_profile_lock_wait_is_bounded_and_retry_recovers():
    import time
    c, data = guest()
    other, _ = guest()
    with engine.connect() as blocker:
        tx = blocker.begin()
        blocker.execute(text('SELECT pg_advisory_xact_lock(7322026, :workspace)'), {'workspace': data['user']['workspace_id']})
        started = time.monotonic()
        response = c.put('/api/v1/auth/profile', json={'role':'admin'})
        elapsed = time.monotonic() - started
        assert response.status_code == 503, response.text
        assert elapsed < 5
        assert response.headers['retry-after'] == '3'
        assert other.get('/api/v1/auth/me').status_code == 200
        assert c.get('/api/v1/auth/me').json()['user']['role'] == 'student'
        tx.rollback()
    assert change(c, 'admin')['user']['role'] == 'admin'

def test_parallel_same_session_role_updates_settle():
    c, data = guest()
    cookie = c.cookies.get('schedule_session')
    def update_role(role):
        with TestClient(app) as client:
            client.cookies.set('schedule_session', cookie)
            return client.put('/api/v1/auth/profile', json={'role':role}, headers={'X-CSRF-Token':data['csrf']}).status_code
    with ThreadPoolExecutor(max_workers=4) as pool:
        statuses = list(pool.map(update_role, ['admin','dispatcher','teacher','student'] * 3))
    assert all(status == 200 for status in statuses), statuses
    assert c.get('/api/v1/auth/me').status_code == 200

@pytest.fixture(autouse=True)
def mode(database,monkeypatch):
    monkeypatch.setenv('GUEST_MODE','1')
    monkeypatch.delenv('PUBLIC_ORIGIN',raising=False)

def guest(role='student'):
    c=TestClient(app)
    c.headers.update({'Origin':'http://testserver','X-Requested-With':'schedule-app'})
    r=c.post('/api/v1/auth/guest',json={'role':role})
    assert r.status_code==200,r.text
    c.headers['X-CSRF-Token']=r.json()['csrf']
    return c,r.json()

def change(c,role,**kwargs):
    r=c.put('/api/v1/auth/profile',json={'role':role,**kwargs})
    assert r.status_code==200,r.text
    return r.json()

def directories(c):
    return {key:c.get('/api/v1/directories/'+key).json() for key in ('groups','teachers','rooms','subjects')}

def lesson(c,day_offset=2,hour=17):
    refs=directories(c)
    schedule=c.get('/api/v1/schedules').json()[0]
    today=datetime.now(MOSCOW).date()
    start=datetime.combine(today+timedelta(days=day_offset),datetime.min.time(),MOSCOW)+timedelta(hours=hour)
    return dict(schedule_id=schedule['id'],group_id=refs['groups'][0]['id'],teacher_id=refs['teachers'][0]['id'],
        room_id=refs['rooms'][0]['id'],subject_id=refs['subjects'][0]['id'],starts=start.isoformat(),ends=(start+timedelta(hours=1)).isoformat())

def rows(c):
    today=datetime.now(MOSCOW).date()
    return c.get('/api/v1/lessons',params={'start':str(today-timedelta(days=7)),'end':str(today+timedelta(days=14))}).json()

@pytest.mark.parametrize('role',['admin','dispatcher','teacher','student'])
def test_guest_auto_creation_role_and_reload(role):
    c,data=guest(role)
    assert data['created'] and data['user']['role']==role and data['user']['is_guest']
    assert 'username' not in data['user'] and 'password' not in data['user']
    again=c.post('/api/v1/auth/guest',json={}).json()
    assert again['user']==data['user'] and again['created'] is False
    assert c.get('/api/v1/auth/me').json()['user']==data['user']
    assert rows(c)['total'] == (41 if role in ('admin','dispatcher') else 40)
    with Factory() as db:
        assert db.scalar(select(func.count()).select_from(Workspace).where(Workspace.kind=='demo'))==1
        assert db.scalar(select(User).where(User.id==data['user']['id'])).password_hash=='!'
        assert db.get(Session,token_hash(c.cookies['schedule_session'])) is not None

def test_bootstrap_security_and_legacy_disabled():
    c=TestClient(app)
    assert c.post('/api/v1/auth/guest',json={}).status_code==403
    assert c.post('/api/v1/auth/guest',json={},headers={'Origin':'https://evil.example','X-Requested-With':'schedule-app'}).status_code==403
    assert c.post('/api/v1/auth/login',json={'username':'admin','password':'test-password'}).status_code==404
    c,data=guest('admin')
    assert c.get('/api/v1/users').status_code==404
    assert c.post('/api/v1/users',json={'username':'nobody','name':'No','role':'admin','password':'test-password'}).status_code==404
    assert c.put('/api/v1/auth/profile',json={'role':'student'},headers={'X-CSRF-Token':''}).status_code==403
    assert c.put('/api/v1/auth/profile',json={'role':'superadmin'}).status_code==422
    assert c.post('/api/v1/auth/guest',json={},headers={'Content-Type':'text/plain'}).status_code in (403,422)

def test_role_roundtrip_preserves_workspace_and_enforces_rights():
    c,data=guest('student')
    refs=directories(c)
    assert c.post('/api/v1/periods',json={'name':'No','start':'2026-10-01','end':'2026-12-01'}).status_code==403
    admin=change(c,'admin',name='Игорь')
    assert admin['user']['workspace_id']==data['user']['workspace_id']
    assert c.post('/api/v1/directories/rooms',json={'name':'Новая аудитория'}).status_code==201
    dispatcher=change(c,'dispatcher')
    assert c.post('/api/v1/directories/rooms',json={'name':'Нельзя'}).status_code==403
    payload=lesson(c)
    created=c.post('/api/v1/lessons',json=payload)
    assert created.status_code==201,created.text
    assert c.post('/api/v1/lessons',json=payload).status_code==409
    teacher=change(c,'teacher',teacher_id=refs['teachers'][1]['id'])
    assert teacher['user']['teacher_id']==refs['teachers'][1]['id']
    assert c.post('/api/v1/lessons',json=payload).status_code==403
    student=change(c,'student',group_id=refs['groups'][1]['id'])
    assert student['user']['group_id']==refs['groups'][1]['id'] and student['user']['teacher_id'] is None
    assert student['user']['name']=='Игорь' and student['user']['id']==data['user']['id']
    assert len(c.get('/api/v1/schedules').json())==1
    assert len(c.get('/api/v1/directories/rooms').json())==4

def test_cross_workspace_reads_writes_history_counts_and_references():
    a,aa=guest('admin'); b,bb=guest('admin')
    assert aa['user']['workspace_id']!=bb['user']['workspace_id']
    da,db=directories(a),directories(b)
    assert {x['id'] for x in da['groups']}.isdisjoint({x['id'] for x in db['groups']})
    assert len(da['groups'])==len(db['groups'])==2
    lb=rows(b)['items'][0]
    assert a.get(f"/api/v1/lessons/{lb['id']}/history").status_code==404
    assert a.post(f"/api/v1/lessons/{lb['id']}/cancel",json={'version':lb['version'],'reason':'foreign'}).status_code==404
    assert a.put(f"/api/v1/directories/groups/{db['groups'][0]['id']}",json={'name':'Stolen'}).status_code==404
    assert a.post(f"/api/v1/schedules/{lb['schedule_id']}/publish").status_code==404
    payload=lesson(a)
    for field,kind in [('group_id','groups'),('teacher_id','teachers'),('room_id','rooms'),('subject_id','subjects')]:
        assert a.post('/api/v1/lessons',json={**payload,field:db[kind][0]['id']}).status_code==404
    assert a.post('/api/v1/lessons',json={**payload,'schedule_id':lb['schedule_id']}).status_code==404
    assert a.put('/api/v1/auth/profile',json={'role':'student','group_id':db['groups'][0]['id']}).status_code==404
    assert a.get('/api/v1/lessons',params={'start':lb['starts'][:10],'end':lb['starts'][:10],'group_id':db['groups'][0]['id']}).json()['total']==0
    assert rows(a)['total']==rows(b)['total']==41
    assert a.post('/api/v1/directories/groups',json={'name':'SharedName'}).status_code==201
    assert b.post('/api/v1/directories/groups',json={'name':'SharedName'}).status_code==201
    # Database itself must reject a mixed-tenant foreign key even without ORM scoping.
    with Factory.begin() as session:
        with pytest.raises(IntegrityError):
            with session.begin_nested():
                session.execute(text('UPDATE users SET group_id=:group_id WHERE id=:user_id'),{'group_id':db['groups'][0]['id'],'user_id':aa['user']['id']})
    with Factory() as session:
        assert session.get(User,1).name=='Admin' and session.get(Workspace,1).kind=='legacy'

def test_series_concurrency_and_idempotence_across_visitors():
    a,_=guest('dispatcher'); b,_=guest('dispatcher')
    pa,pb=lesson(a),lesson(b)
    def save(pair):
        c,payload=pair
        return c.post('/api/v1/lessons',json=payload).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(save,[(a,pa),(b,pb)]))==[201,201]
    for c in (a,b):
        data=lesson(c,hour=19)
        data.update(until=(datetime.fromisoformat(data['starts']).date()+timedelta(days=14)).isoformat(),interval_weeks=1,request_key='same-key')
        r=c.post('/api/v1/series',json=data)
        assert r.status_code==201,r.text
        assert len(r.json()['lesson_ids'])==3
        assert c.post('/api/v1/series',json=data).json()['replayed'] is True

def test_reset_expiry_cleanup_and_csrf():
    a,aa=guest('admin'); b,bb=guest('student')
    old_cookie=a.cookies['schedule_session']
    assert a.post('/api/v1/auth/guest/reset',json={},headers={'X-CSRF-Token':''}).status_code==403
    reset=a.post('/api/v1/auth/guest/reset',json={})
    assert reset.status_code==200,reset.text
    assert reset.json()['user']['workspace_id']!=aa['user']['workspace_id']
    assert a.cookies['schedule_session']!=old_cookie
    assert b.get('/api/v1/auth/me').status_code==200
    with Factory.begin() as db:
        assert db.get(Workspace,aa['user']['workspace_id']) is None
        ws=db.get(Workspace,bb['user']['workspace_id']); ws.expires=datetime.now(timezone.utc)-timedelta(seconds=1)
    assert b.get('/api/v1/auth/me').status_code==401
    guest()
    with Factory() as db:
        assert db.get(Workspace,bb['user']['workspace_id']) is None
        assert db.get(Workspace,1) is not None

def test_guest_limits_and_cookie_flags(monkeypatch):
    import app.main as main
    import app.workspaces as scoped
    a,data=guest('admin')
    monkeypatch.setitem(scoped.LIMITS,Group,2)
    assert a.post('/api/v1/directories/groups',json={'name':'Too many'}).status_code==422
    with Factory.begin() as db:
        key=token_hash('guest:testclient')
        db.add_all([LoginAttempt(key=key) for _ in range(9)])
    c=TestClient(app,headers={'Origin':'http://testserver','X-Requested-With':'schedule-app'})
    assert c.post('/api/v1/auth/guest',json={}).status_code==429
    assert a.post('/api/v1/auth/guest',json={}).status_code==200
    monkeypatch.setattr(main,'PRODUCTION',True)
    monkeypatch.setattr(main,'COOKIE_PATH','/mireabackr')
    with Factory.begin() as db: db.execute(text('DELETE FROM login_attempts'))
    c=TestClient(app,base_url='https://testserver',headers={'Origin':'https://testserver','X-Requested-With':'schedule-app'})
    r=c.post('/api/v1/auth/guest',json={})
    assert r.status_code==200,r.text
    cookie=r.headers['set-cookie'].lower()
    assert all(flag in cookie for flag in ('secure','httponly','samesite=strict','path=/mireabackr','max-age=604'))

def test_reset_at_capacity_and_bulk_scope_guard(monkeypatch):
    import app.demo as demo
    a,data=guest('admin')
    monkeypatch.setattr(demo,'MAX_WORKSPACES',1)
    assert a.post('/api/v1/auth/guest/reset',json={}).status_code==200
    with Factory.begin() as db:
        db.info['workspace_id']=data['user']['workspace_id']
        for statement in (update(Group).values(name='oops'),delete(Group)):
            with pytest.raises(HTTPException): db.execute(statement)

def test_legacy_session_is_rejected_and_guest_token_expires():
    with Factory.begin() as db:
        db.add(Session(token_hash=token_hash('legacy-cookie'),user_id=1,csrf='legacy-csrf',expires=datetime.now(timezone.utc)+timedelta(hours=1)))
    c=TestClient(app); c.cookies.set('schedule_session','legacy-cookie')
    assert c.get('/api/v1/auth/me').status_code==401
    c,data=guest()
    with Factory.begin() as db:
        db.get(Session,token_hash(c.cookies['schedule_session'])).expires=datetime.now(timezone.utc)-timedelta(seconds=1)
    assert c.get('/api/v1/auth/me').status_code==401
