from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError
from sqlalchemy import select,func
from test_api import database, engine, app, client
from test_guest import mode,guest,lesson,rows,Factory
from app.bootstrap import limiter
from app.models import Workspace,User,Session,Lesson,Audit,Series,Group,Teacher,Room,Subject,Period,Schedule
from app.adapters.db.schedule_repository import ScheduleRepository
from app.domain.errors import DependencyUnavailable

def counts():
    with Factory() as db:
        return {model.__tablename__:db.scalar(select(func.count()).select_from(model)) for model in (Workspace,User,Session,Lesson,Audit,Series,Group,Teacher,Room,Subject,Period,Schedule)}

def test_runtime_redis_outage_keeps_reads_and_preview_but_blocks_every_write(monkeypatch):
    c,data=guest('admin')
    payload=lesson(c,hour=18)
    existing=rows(c)['items'][0]
    before=counts()
    series=payload | {'until':payload['starts'][:10],'request_key':'outage-series'}
    original=limiter.client.evalsha
    def unavailable(*args,**kwargs): raise ConnectionError('isolated outage')
    monkeypatch.setattr(limiter.client,'evalsha',unavailable)
    assert c.get('/api/v1/health').status_code==200
    assert c.get('/api/v1/auth/me').json()['user']==data['user']
    assert c.get('/api/v1/schedules').status_code==200
    assert c.get('/api/v1/periods').status_code==200
    assert c.get('/api/v1/directories/groups').status_code==200
    assert rows(c)['total']==41
    assert c.get(f"/api/v1/lessons/{existing['id']}/history").status_code==200
    assert c.post('/api/v1/series/preview',json=series).status_code==200
    assert c.post('/api/v1/auth/guest',json={}).json()['created'] is False
    writes=[
        ('post','/api/v1/directories/groups',{'name':'new'}),
        ('put',f"/api/v1/directories/groups/{payload['group_id']}",{'name':'new'}),
        ('post','/api/v1/periods',{'name':'new','start':'2026-10-01','end':'2026-12-01'}),
        ('post','/api/v1/schedules',{'name':'new','period_id':1}),
        ('post',f"/api/v1/schedules/{payload['schedule_id']}/publish",None),
        ('post','/api/v1/lessons',payload),
        ('put',f"/api/v1/lessons/{existing['id']}",payload | {'reason':'move','version':existing['version']}),
        ('post',f"/api/v1/lessons/{existing['id']}/cancel",{'reason':'cancel','version':existing['version']}),
        ('post','/api/v1/series',series),
        ('put','/api/v1/auth/profile',{'role':'teacher'}),
        ('post','/api/v1/auth/guest/reset',{}),
        ('post','/api/v1/auth/logout',None),
    ]
    for method,path,body in writes:
        response=getattr(c,method)(path,json=body)
        assert response.status_code==503,(path,response.text)
        assert response.headers['retry-after']=='3'
    newcomer=TestClient(app,headers={'Origin':'http://testserver','X-Requested-With':'schedule-app'})
    assert newcomer.post('/api/v1/auth/guest',json={}).status_code==503
    assert counts()==before
    assert c.get('/api/v1/auth/me').json()['user']==data['user']
    monkeypatch.setattr(limiter.client,'evalsha',original)
    assert c.put('/api/v1/auth/profile',json={'role':'teacher'}).status_code==200

def test_login_and_user_mutations_fail_closed(monkeypatch):
    monkeypatch.setenv('GUEST_MODE','0')
    c=client()
    before=counts()
    def unavailable(*args,**kwargs): raise ConnectionError('isolated outage')
    monkeypatch.setattr(limiter.client,'evalsha',unavailable)
    assert TestClient(app).post('/api/v1/auth/login',json={'username':'admin','password':'test-password'}).status_code==503
    assert c.post('/api/v1/users',json={'username':'second','name':'Second','password':'test-password','role':'admin'}).status_code==503
    assert c.post('/api/v1/users/2/toggle').status_code==503
    assert c.get('/api/v1/users').status_code==200
    assert counts()==before

def test_audit_failure_rolls_back_lesson_and_series_midway(monkeypatch):
    c,_=guest('dispatcher')
    payload=lesson(c,hour=19)
    before=counts()
    original=ScheduleRepository.append_audit
    def failure(self,*args,**kwargs):
        original(self,*args,**kwargs)
        raise DependencyUnavailable('injected-after-audit')
    monkeypatch.setattr(ScheduleRepository,'append_audit',failure)
    assert c.post('/api/v1/lessons',json=payload).status_code==503
    assert counts()==before
    monkeypatch.setattr(ScheduleRepository,'append_audit',original)
    insert=ScheduleRepository.insert_lesson
    calls=[]
    def second_failure(self,*args,**kwargs):
        calls.append(1)
        if len(calls)==2: raise DependencyUnavailable('injected-second-lesson')
        return insert(self,*args,**kwargs)
    monkeypatch.setattr(ScheduleRepository,'insert_lesson',second_failure)
    series=payload | {'until':(datetime.fromisoformat(payload['starts']).date()+timedelta(days=14)).isoformat(),'request_key':'rollback-series'}
    assert c.post('/api/v1/series',json=series).status_code==503
    assert len(calls)==2 and counts()==before
