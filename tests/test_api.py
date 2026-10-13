import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError
from app.db import DATABASE_URL, APP_ENV, Base, get_db
from sqlalchemy.engine import make_url
from app.main import app
from app.bootstrap import limiter, provide_services
from app.api.dependencies import get_services
from app.application.common import bucket
from app.models import User, Group, Teacher, Room, Subject, Period, Schedule, Lesson, Session, LoginAttempt, Workspace
from app.security import password_hash

# Only the dedicated test database is ever cleared.
url=make_url(DATABASE_URL).set(database='schedule_test')
if APP_ENV not in ('development', 'test') or url.host not in ('127.0.0.1', 'localhost') or url.database != 'schedule_test':
    raise RuntimeError('Tests require a local development/test database named schedule_test')
engine=create_engine(url)
Factory=sessionmaker(engine,expire_on_commit=False,info={'workspace_id':1})

@pytest.fixture(autouse=True)
def database(monkeypatch):
    monkeypatch.setenv('GUEST_MODE','0')
    app.dependency_overrides[get_services]=provide_services
    for key in limiter.client.scan_iter(match=limiter.namespace+':*'):
        limiter.client.delete(key)
    if engine.url.database != 'schedule_test':
        raise RuntimeError('Refusing to clear a non-test database')
    with engine.begin() as connection:
        connection.execute(text('CREATE EXTENSION IF NOT EXISTS btree_gist'))
        Base.metadata.create_all(connection)
        names=','.join('"'+t.name+'"' for t in Base.metadata.sorted_tables)
        connection.execute(text(f'TRUNCATE {names} RESTART IDENTITY CASCADE'))
    with Factory.begin() as db:
        db.add(Workspace(id=1,kind='legacy')); db.flush()
        db.execute(text("SELECT setval(pg_get_serial_sequence('workspaces','id'),1,true)"))
        db.add_all([Group(name='G1',size=20),Group(name='G2',size=20),Teacher(name='T1'),Teacher(name='T2'),Room(name='R1',capacity=25),Room(name='R2',capacity=25),Room(name='Small',capacity=10),Subject(name='S1')]); db.flush()
        db.add_all([User(username='admin',name='Admin',role='admin',password_hash=password_hash('test-password')),User(username='student',name='Student',role='student',group_id=1,password_hash=password_hash('test-password'))]); db.flush()
        db.add(Period(name='Semester',start=datetime(2026,9,1).date(),end=datetime(2026,12,31).date())); db.flush()
        db.add_all([Schedule(name='Draft',period_id=1,author_id=1),Schedule(name='Other',period_id=1,author_id=1)])
    def override():
        with Factory() as db:
            db.info.clear()
            try:
                yield db; db.commit()
            except Exception:
                db.rollback(); raise
    app.dependency_overrides[get_db]=override
    yield
    app.dependency_overrides.clear()

def client(role='admin'):
    c=TestClient(app)
    result=c.post('/api/v1/auth/login',json={'username':role,'password':'test-password'})
    assert result.status_code==200
    c.headers['X-CSRF-Token']=result.json()['csrf']
    return c

def lesson(**kwargs):
    return dict(schedule_id=1,group_id=1,teacher_id=1,room_id=1,subject_id=1,starts='2026-10-05T09:00:00+03:00',ends='2026-10-05T10:30:00+03:00',**{}) | kwargs

def test_auth_csrf_logout():
    c=TestClient(app)
    assert c.get('/api/v1/periods').status_code==401
    c=client(); saved=c.cookies.get('schedule_session')
    assert c.post('/api/v1/lessons',json=lesson(),headers={'X-CSRF-Token':''}).status_code==403
    assert c.post('/api/v1/lessons',json=lesson(),headers={'Origin':'https://evil.example'}).status_code==403
    assert c.post('/api/v1/auth/logout').status_code==200
    c.cookies.set('schedule_session',saved)
    assert c.get('/api/v1/auth/me').status_code==401

def test_permissions_and_publication():
    a,s=client(),client('student')
    result=a.post('/api/v1/lessons',json=lesson()); assert result.status_code==201
    assert s.post('/api/v1/lessons',json=lesson()).status_code==403
    assert s.get('/api/v1/users').status_code==403
    assert s.get('/api/v1/schedules').json()==[]
    assert s.get('/api/v1/lessons/1/history').status_code==404
    assert s.get('/api/v1/lessons?start=2026-10-01&end=2026-10-10').json()['total']==0
    assert a.post('/api/v1/schedules/1/publish').status_code==200
    assert s.get('/api/v1/lessons?start=2026-10-01&end=2026-10-10').json()['total']==1
    assert len(s.get('/api/v1/lessons/1/history').json())==1

@pytest.mark.parametrize('change',[{'group_id':2,'teacher_id':2},{'group_id':2,'room_id':2},{'teacher_id':2,'room_id':2}])
def test_each_resource_conflict(change):
    c=client(); assert c.post('/api/v1/lessons',json=lesson()).status_code==201
    r=c.post('/api/v1/lessons',json=lesson(**change)); assert r.status_code==409
    assert len(r.json()['detail']['conflicts'])==1

def test_adjacent_and_capacity_and_date_rules():
    c=client()
    assert c.post('/api/v1/lessons',json=lesson()).status_code==201
    assert c.post('/api/v1/lessons',json=lesson(starts='2026-10-05T10:30:00+03:00',ends='2026-10-05T12:00:00+03:00')).status_code==201
    assert c.post('/api/v1/lessons',json=lesson(room_id=3)).status_code==422
    assert c.post('/api/v1/lessons',json=lesson(starts='2027-10-05T09:00:00+03:00',ends='2027-10-05T10:30:00+03:00')).status_code==422
    assert c.post('/api/v1/lessons',json=lesson(starts='2026-10-05T10:31:00+03:00')).status_code==422
    assert c.post('/api/v1/lessons',json=lesson(starts='2026-10-05T09:00:00')).status_code==422

def test_series_preview_idempotence_and_payload_mismatch():
    c=client(); data=lesson() | {'until':'2026-11-02','interval_weeks':2,'request_key':'test-series-key'}
    preview=c.post('/api/v1/series/preview',json=data); assert preview.status_code==200
    assert len(preview.json()['items'])==3 and preview.json()['can_save']
    first=c.post('/api/v1/series',json=data); assert first.status_code==201
    second=c.post('/api/v1/series',json=data); assert second.json()['replayed']
    assert first.json()['lesson_ids']==second.json()['lesson_ids']
    assert c.post('/api/v1/series',json=data | {'interval_weeks':1}).status_code==409

def test_series_atomic_failure():
    c=client(); c.post('/api/v1/lessons',json=lesson(starts='2026-10-12T09:00:00+03:00',ends='2026-10-12T10:30:00+03:00'))
    data=lesson() | {'until':'2026-10-19','interval_weeks':1,'request_key':'atomic-series-key'}
    assert c.post('/api/v1/series/preview',json=data).json()['can_save'] is False
    assert c.post('/api/v1/series',json=data).status_code==409
    assert c.get('/api/v1/lessons?start=2026-10-01&end=2026-10-31').json()['total']==1

def test_move_cancel_version_and_history():
    c=client(); c.post('/api/v1/lessons',json=lesson())
    change=lesson(starts='2026-10-06T09:00:00+03:00',ends='2026-10-06T10:30:00+03:00') | {'reason':'Перенос по просьбе преподавателя','version':1}
    assert c.put('/api/v1/lessons/1',json=change).json()['version']==2
    assert c.put('/api/v1/lessons/1',json=change).status_code==409
    assert c.post('/api/v1/lessons/1/cancel',json={'reason':'Болезнь преподавателя','version':2}).status_code==200
    assert c.post('/api/v1/lessons',json={k:v for k,v in change.items() if k not in ('reason','version')}).status_code==201
    assert [x['action'] for x in c.get('/api/v1/lessons/1/history').json()]==['cancelled','moved','created']

def test_direct_database_exclusion_and_concurrency():
    def write():
        try:
            with Factory.begin() as db:
                data=lesson(); data['starts']=datetime.fromisoformat(data['starts']); data['ends']=datetime.fromisoformat(data['ends'])
                db.add(Lesson(**data)); db.flush()
            return 'saved'
        except IntegrityError:
            return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as executor:
        results=list(executor.map(lambda _:write(),range(2)))
    assert sorted(results)==['conflict','saved']

def test_api_concurrent_writers():
    a,b=client(),client()
    with ThreadPoolExecutor(max_workers=2) as executor:
        results=list(executor.map(lambda c:c.post('/api/v1/lessons',json=lesson()).status_code,[a,b]))
    assert sorted(results)==[201,409]

def test_empty_publish_limits_and_user_disable():
    a,s=client(),client('student')
    assert a.post('/api/v1/schedules/1/publish').status_code==422
    assert a.get('/api/v1/lessons?start=2026-01-01&end=2026-12-31').status_code==422
    assert a.post('/api/v1/users/1/toggle').status_code==422
    assert a.post('/api/v1/users/2/toggle').status_code==200
    assert s.get('/api/v1/auth/me').status_code==401

def test_login_throttle():
    c=TestClient(app)
    for _ in range(10):
        assert c.post('/api/v1/auth/login',json={'username':'nobody','password':'bad'}).status_code==401
    assert c.post('/api/v1/auth/login',json={'username':'nobody','password':'bad'}).status_code==429

def test_archive_and_directory_admin_only():
    c,s=client(),client('student')
    assert s.post('/api/v1/directories/rooms',json={'name':'R3'}).status_code==403
    assert c.put('/api/v1/directories/rooms/1',json={'name':'R1','capacity':25,'active':False}).status_code==200
    assert c.post('/api/v1/lessons',json=lesson()).status_code==422
    assert c.post('/api/v1/directories/rooms',json={'name':'R1'}).status_code==409


def test_body_limit_and_chunked_body():
    c=TestClient(app)
    assert c.post('/api/v1/auth/login',content=b'x'*65537).status_code==413
    assert c.post('/api/v1/auth/login',content=iter([b'x'*40000,b'y'*40000])).status_code==413


def test_ip_limit_blocks_username_rotation_and_cleans_old_rows():
    with Factory.begin() as db:
        db.add(LoginAttempt(key='expired',created=datetime.now(timezone.utc)-timedelta(days=2)))
    c=TestClient(app)
    for i in range(60):
        assert c.post('/api/v1/auth/login',json={'username':f'nobody{i}','password':'bad'}).status_code==401
    assert c.post('/api/v1/auth/login',json={'username':'rotated','password':'bad'}).status_code==429
    with Factory() as db:
        assert db.scalar(select(LoginAttempt).where(LoginAttempt.key=='expired')) is not None  # legacy rows are unused, retained for rollback
    assert int(limiter.client.get(limiter.key(bucket('ip','ip:testclient',60,900)))) == 60


def test_sessions_are_capped_and_expire():
    first=client()
    for _ in range(5):
        client()
    assert first.get('/api/v1/auth/me').status_code==401
    last=client()
    with Factory.begin() as db:
        records=list(db.scalars(select(Session).where(Session.user_id==1)))
        assert len(records)==5
        for record in records:
            record.expires=datetime.now(timezone.utc)-timedelta(seconds=1)
    assert last.get('/api/v1/auth/me').status_code==401


def test_atomic_login_limit():
    def attempt(_):
        return TestClient(app).post('/api/v1/auth/login',json={'username':'parallel','password':'bad'}).status_code
    with ThreadPoolExecutor(max_workers=12) as pool:
        results=list(pool.map(attempt, range(12)))
    assert results.count(401)==10 and results.count(429)==2


def test_filters_and_dispatcher_rights():
    a=client()
    assert a.post('/api/v1/users',json={'username':'dispatcher','name':'Dispatcher','password':'test-password','role':'dispatcher'}).status_code==201
    d=client('dispatcher')
    assert d.post('/api/v1/directories/rooms',json={'name':'No'}).status_code==403
    assert d.post('/api/v1/lessons',json=lesson()).status_code==201
    assert d.get('/api/v1/lessons?start=2026-10-05&end=2026-10-05&group_id=2').json()['total']==0
    assert d.get('/api/v1/lessons?start=2026-10-05&end=2026-10-05&teacher_id=1&room_id=1').json()['total']==1


def test_production_cookie_flags(monkeypatch):
    import app.api.config as main
    monkeypatch.setattr(main,'PRODUCTION',True)
    monkeypatch.setattr(main,'COOKIE_PATH','/mireabackr')
    c=TestClient(app,base_url='https://testserver')
    response=c.post('/api/v1/auth/login',json={'username':'admin','password':'test-password'})
    assert response.status_code==200
    cookie=response.headers['set-cookie'].lower()
    assert 'secure' in cookie and 'httponly' in cookie and 'samesite=strict' in cookie
    assert 'path=/mireabackr' in cookie
    assert response.headers['x-frame-options']=='DENY'
    headers={'Cookie':'schedule_session='+response.cookies['schedule_session'],'X-CSRF-Token':response.json()['csrf']}
    assert 'path=/mireabackr' in c.post('/api/v1/auth/logout',headers=headers).headers['set-cookie'].lower()


def test_extreme_query_date_rejected_and_public_schedule_is_shared():
    a,s=client(),client('student')
    assert a.get('/api/v1/lessons?start=9999-12-31&end=9999-12-31').status_code==422
    assert a.post('/api/v1/lessons',json=lesson(group_id=2)).status_code==201
    assert a.post('/api/v1/schedules/1/publish').status_code==200
    # Published teaching timetable is intentionally common to all authenticated users.
    assert s.get('/api/v1/lessons?start=2026-10-05&end=2026-10-05&group_id=2').json()['total']==1
