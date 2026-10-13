"""Exercise only fresh, disposable private demos; never touch legacy records."""
import sys, uuid, time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import httpx

base=sys.argv[1].rstrip('/')
origin=str(httpx.URL(base).copy_with(path='',query=None)) .rstrip('/')
headers={'Origin':origin,'X-Requested-With':'schedule-app'}
checks=[]
def request(client, method, path, body=None, expected=200):
    time.sleep(.08)
    r=client.request(method,base+'/api/v1'+path,json=body)
    assert r.status_code==expected, (method,path,r.status_code,r.text[:300])
    return r.json()
def mark(label):
    checks.append(label); print('PASS '+label,flush=True)
with httpx.Client(headers=headers,timeout=20) as a, httpx.Client(headers=headers,timeout=20) as b:
    first=request(a,'POST','/auth/guest',{})
    a.headers['X-CSRF-Token']=first['csrf']
    assert first['user']['role']=='student' and first['user']['is_guest']
    again=request(a,'POST','/auth/guest',{})
    assert again['user']['id']==first['user']['id']
    other=request(b,'POST','/auth/guest',{})
    b.headers['X-CSRF-Token']=other['csrf']
    assert first['user']['workspace_id']!=other['user']['workspace_id']
    mark('automatic entry, reload and independent visitors')
    if base.startswith('https:'):
        cookie=next(c for c in a.cookies.jar if c.name=='schedule_session')
        assert cookie.secure and cookie.has_nonstandard_attr('HttpOnly') and str(cookie.get_nonstandard_attr('SameSite')).lower()=='strict'
        assert cookie.path=='/mireabackr'
        mark('secure scoped session cookie')
    request(a,'POST','/auth/login',{'username':'not-an-account','password':'not-a-password'},404)
    request(a,'GET','/users',expected=403)
    request(a,'POST','/directories/groups',{'name':'forbidden','size':20},403)
    for role in ('teacher','dispatcher','admin','student','admin'):
        changed=request(a,'PUT','/auth/profile',{'role':role,'name':'Проверка демо'})
        assert changed['user']['id']==first['user']['id'] and changed['user']['role']==role
    mark('four roles, legacy login disabled, student cannot edit')
    request(a,'GET','/users',expected=404)
    dirs={kind:request(a,'GET','/directories/'+kind) for kind in ('groups','teachers','rooms','subjects')}
    foreign=request(b,'GET','/directories/groups')[0]['id']
    request(a,'PUT','/directories/groups/'+str(foreign),{'name':'forbidden','size':20,'active':True},404)
    group=request(a,'POST','/directories/groups',{'name':'Проверочная группа','size':20},201)
    assert group['id'] not in [x['id'] for x in request(b,'GET','/directories/groups')]
    mark('directory creation and cross-workspace isolation')
    today=datetime.now(ZoneInfo('Europe/Moscow')).date()
    period=request(a,'POST','/periods',{'name':'Проверочный период','start':str(today),'end':str(today+timedelta(days=30))},201)
    schedule=request(a,'POST','/schedules',{'name':'Проверочный черновик','period_id':period['id']},201)
    lesson=dict(schedule_id=schedule['id'],group_id=group['id'],teacher_id=dirs['teachers'][0]['id'],room_id=dirs['rooms'][0]['id'],subject_id=dirs['subjects'][0]['id'],starts=f'{today}T19:00:00+03:00',ends=f'{today}T20:00:00+03:00')
    item=request(a,'POST','/lessons',lesson,201)
    request(a,'POST','/lessons',lesson,409)
    request(a,'POST',f"/schedules/{schedule['id']}/publish",{})
    moved=request(a,'PUT',f"/lessons/{item['id']}",lesson|{'starts':f'{today}T20:00:00+03:00','ends':f'{today}T21:00:00+03:00','version':item['version'],'reason':'Проверка переноса'})
    request(a,'POST',f"/lessons/{item['id']}/cancel",{'version':moved['version'],'reason':'Проверка отмены'})
    history=request(a,'GET',f"/lessons/{item['id']}/history")
    assert {x['action'] for x in history}>={'created','moved','cancelled'}
    request(b,'GET',f"/lessons/{item['id']}/history",expected=404)
    mark('draft, conflict, publication, move, cancellation and history')
    series=lesson|{'starts':f'{today}T21:00:00+03:00','ends':f'{today}T22:00:00+03:00','until':str(today+timedelta(days=14)),'interval_weeks':1,'request_key':uuid.uuid4().hex}
    preview=request(a,'POST','/series/preview',series)
    assert preview['can_save'] and len(preview['items'])==3
    created=request(a,'POST','/series',series,201)
    replay=request(a,'POST','/series',series,201)
    assert replay['replayed'] and replay['lesson_ids']==created['lesson_ids']
    mark('recurring series preview, save and idempotent replay')
    reset=request(a,'POST','/auth/guest/reset',{})
    a.headers['X-CSRF-Token']=reset['csrf']
    assert reset['user']['workspace_id']!=first['user']['workspace_id']
    assert request(b,'GET','/auth/me')['user']['id']==other['user']['id']
    assert 'Проверочная группа' not in [x['name'] for x in request(a,'GET','/directories/groups')]
    mark('reset affects own demo only')
print(f'GUEST_SMOKE_OK {len(checks)} scenario groups')
