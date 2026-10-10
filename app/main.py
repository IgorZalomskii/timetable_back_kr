import hashlib
import json
import logging
import os
import secrets
from datetime import date, datetime, timedelta, timezone
from fastapi import FastAPI, Depends, HTTPException, Request, Response, Query
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, func, delete, text
from sqlalchemy.exc import IntegrityError, OperationalError, TimeoutError as PoolTimeoutError
from .db import get_db, ROOT, APP_ENV
from .limits import BodyLimit
from .models import User, Session, LoginAttempt, Group, Room, Teacher, Subject, Period, Schedule, Series, Lesson, Audit, Workspace
from .schemas import LoginIn, DirectoryIn, UserIn, PeriodIn, ScheduleIn, LessonIn, SeriesIn, ChangeIn, CancelIn, GuestIn, ProfileIn
from .security import current_user, editor, admin, password_hash, verify_password, token_hash, user_view, guest_mode
from .demo import reserve_creation, seed_workspace, make_session
from .services import DIRECTORIES, MOSCOW, lock_writes, require, snapshot, audit, validate_lesson, expand_series, create_lesson

PRODUCTION = APP_ENV == 'production'
COOKIE_PATH = os.environ.get('APP_BASE_PATH', '/').rstrip('/') or '/'
DUMMY_HASH = password_hash('non-user-timing-placeholder')
app = FastAPI(title='Расписание — сервер учебного расписания', version='2.0.0', docs_url='/docs' if not PRODUCTION else None, redoc_url=None, openapi_url='/openapi.json' if not PRODUCTION else None)
app.add_middleware(BodyLimit)

@app.middleware('http')
async def headers(request: Request, call_next):
    # Same-origin browser requests only; command-line clients can use cookie + CSRF.
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        origin = request.headers.get('origin')
        expected = os.environ.get('PUBLIC_ORIGIN', str(request.base_url).rstrip('/'))
        if origin and origin != expected:
            return JSONResponse({'detail':'Недопустимый источник запроса'}, status_code=403)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    if PRODUCTION:
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; base-uri 'self'"
    response.headers['Referrer-Policy'] = 'same-origin'
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    return response

@app.exception_handler(IntegrityError)
async def database_conflict(request, exc):
    return JSONResponse({'detail':'Данные конфликтуют с существующей записью. Обновите список и проверьте занятость и уникальность названия.'}, status_code=409)

@app.exception_handler(OperationalError)
@app.exception_handler(PoolTimeoutError)
async def database_unavailable(request, exc):
    # Do not log SQL text, parameters, cookies, or connection strings.
    logging.getLogger('schedule.database').warning('Database unavailable: method=%s path=%s error=%s sqlstate=%s', request.method, request.url.path, type(exc).__name__, getattr(getattr(exc, 'orig', None), 'sqlstate', None))
    return JSONResponse({'detail':'Сервер занят или база временно недоступна. Подождите несколько секунд и проверьте состояние данных.'}, status_code=503, headers={'Retry-After':'3'})

@app.get('/api/v1/health')
def health(db=Depends(get_db)):
    db.execute(text('SELECT 1'))
    return {'status':'ok'}

def guest_request(request):
    if not guest_mode():
        raise HTTPException(404)
    expected=os.environ.get('PUBLIC_ORIGIN',str(request.base_url).rstrip('/'))
    if (request.headers.get('origin') != expected or
        request.headers.get('x-requested-with') != 'schedule-app' or
        not request.headers.get('content-type','').startswith('application/json')):
        raise HTTPException(403,'Откройте приложение на его сайте и повторите действие')

def session_view(user, session, created=False):
    return {'user':user_view(user),'csrf':session.csrf,'expires_at':session.expires,'created':created}

def guest_cookie(response, raw, session):
    remaining=max(1,int((session.expires-datetime.now(timezone.utc)).total_seconds()))
    response.set_cookie('schedule_session',raw,httponly=True,secure=PRODUCTION,samesite='strict',max_age=remaining,path=COOKIE_PATH)

@app.post('/api/v1/auth/guest')
def guest(data: GuestIn, request: Request, response: Response, db=Depends(get_db)):
    guest_request(request)
    now=datetime.now(timezone.utc)
    session=db.get(Session,token_hash(request.cookies.get('schedule_session','')))
    if session and session.expires>now:
        user=db.get(User,session.user_id)
        workspace=db.get(Workspace,user.workspace_id) if user else None
        if user and user.is_guest and user.active and workspace and workspace.kind=='demo' and workspace.expires>now:
            return session_view(user,session)
    reserve_creation(db,request)
    workspace,user=seed_workspace(db,data.role)
    raw,session=make_session(db,user,workspace)
    guest_cookie(response,raw,session)
    return session_view(user,session,True)

@app.put('/api/v1/auth/profile')
def profile(data: ProfileIn, request: Request, user=Depends(current_user), db=Depends(get_db)):
    if not user.is_guest:
        raise HTTPException(403,'Выбор роли доступен только в личной демонстрации')
    group_id=teacher_id=None
    for role, model, field in [('student',Group,'group_id'),('teacher',Teacher,'teacher_id')]:
        if data.role != role:
            continue
        ident=getattr(data,field)
        obj=require(db,model,ident) if ident is not None else db.scalar(select(model).where(model.active==True).order_by(model.id).limit(1))
        if obj is None or not obj.active:
            raise HTTPException(422,'Сначала добавьте активную группу или преподавателя в справочник')
        if role=='student': group_id=obj.id
        else: teacher_id=obj.id
    user.role=data.role; user.group_id=group_id; user.teacher_id=teacher_id
    if data.name is not None: user.name=data.name
    db.flush()
    return session_view(user,request.state.session)

@app.post('/api/v1/auth/guest/reset')
def reset_guest(request: Request,response: Response,user=Depends(current_user),db=Depends(get_db)):
    guest_request(request)
    if not user.is_guest or request.state.workspace.kind!='demo':
        raise HTTPException(403)
    role=user.role
    old_workspace=user.workspace_id
    reserve_creation(db,request,replacing=old_workspace)
    db.execute(delete(Workspace).where(Workspace.id==old_workspace,Workspace.kind=='demo'))
    db.expunge_all(); db.info.clear()
    workspace,user=seed_workspace(db,role)
    raw,session=make_session(db,user,workspace)
    guest_cookie(response,raw,session)
    return session_view(user,session,True)

@app.post('/api/v1/auth/login')
def login(data: LoginIn, request: Request, response: Response, db=Depends(get_db)):
    if guest_mode():
        raise HTTPException(404)
    now = datetime.now(timezone.utc)
    # Reserve attempts atomically, independent IP/account keys prevent name rotation.
    db.execute(text('SELECT pg_advisory_xact_lock(7322027)'))
    db.execute(delete(LoginAttempt).where(LoginAttempt.created < now-timedelta(minutes=15)))
    db.execute(delete(Session).where(Session.expires < now))
    keys = [(token_hash('ip:'+(request.client.host if request.client else 'unknown')), 60),
            (token_hash('account:'+data.username.lower()), 10)]
    for key, limit in keys:
        attempts = db.scalar(select(func.count()).select_from(LoginAttempt).where(LoginAttempt.key==key))
        if attempts >= limit:
            db.commit()
            raise HTTPException(429, 'Слишком много попыток. Повторите через 15 минут.')
    for key, _ in keys:
        db.add(LoginAttempt(key=key))
    db.commit()
    user = db.scalar(select(User).where(User.username == data.username))
    valid = verify_password(data.password, user.password_hash if user else DUMMY_HASH)
    if not user or not user.active or not valid:
        raise HTTPException(401, 'Неверный логин или пароль')
    # Lock user while capping concurrent sessions; recheck an intervening disable.
    db.refresh(user, with_for_update=True)
    if not user.active:
        raise HTTPException(401, 'Учётная запись отключена')
    old_token = request.cookies.get('schedule_session')
    if old_token:
        db.execute(delete(Session).where(Session.token_hash == token_hash(old_token)))
    excess = list(db.scalars(select(Session.token_hash).where(Session.user_id==user.id).order_by(Session.expires.desc()).offset(4)))
    if excess:
        db.execute(delete(Session).where(Session.token_hash.in_(excess)))
    raw, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    db.add(Session(token_hash=token_hash(raw), user_id=user.id, csrf=csrf, expires=now+timedelta(hours=8)))
    response.set_cookie('schedule_session', raw, httponly=True, secure=PRODUCTION, samesite='strict', max_age=28800, path=COOKIE_PATH)
    return {'user':user_view(user), 'csrf':csrf}

@app.get('/api/v1/auth/me')
def me(request: Request, user=Depends(current_user)):
    return session_view(user,request.state.session)

@app.post('/api/v1/auth/logout')
def logout(request: Request, response: Response, user=Depends(current_user), db=Depends(get_db)):
    db.delete(request.state.session)
    response.delete_cookie('schedule_session', path=COOKIE_PATH)
    return {'ok':True}

def directory_view(obj):
    return {column.name:getattr(obj,column.name) for column in obj.__table__.columns if column.name!='workspace_id'}

@app.get('/api/v1/directories/{kind}')
def directory_list(kind: str, user=Depends(current_user), db=Depends(get_db)):
    model = DIRECTORIES.get(kind)
    if not model:
        raise HTTPException(404, 'Справочник не найден')
    return [directory_view(x) for x in db.scalars(select(model).order_by(model.name))]

@app.post('/api/v1/directories/{kind}', status_code=201)
def directory_create(kind: str, data: DirectoryIn, user=Depends(admin), db=Depends(get_db)):
    model = DIRECTORIES.get(kind)
    if not model:
        raise HTTPException(404, 'Справочник не найден')
    values = {k:v for k,v in data.model_dump().items() if k in model.__table__.columns}
    obj = model(**values)
    db.add(obj)
    db.flush()
    return directory_view(obj)

@app.put('/api/v1/directories/{kind}/{ident}')
def directory_update(kind: str, ident: int, data: DirectoryIn, user=Depends(admin), db=Depends(get_db)):
    model = DIRECTORIES.get(kind)
    if not model:
        raise HTTPException(404, 'Справочник не найден')
    lock_writes(db)
    obj = require(db, model, ident)
    fk = {'groups':'group_id','teachers':'teacher_id','rooms':'room_id','subjects':'subject_id'}[kind]
    future = list(db.scalars(select(Lesson).where(getattr(Lesson, fk)==ident, Lesson.ends > datetime.now(timezone.utc), Lesson.status!='cancelled')))
    if future and not data.active:
        raise HTTPException(409, 'Сначала перенесите или отмените будущие занятия этой записи')
    if kind == 'groups' and any(db.get(Room, x.room_id).capacity < data.size for x in future):
        raise HTTPException(409, 'Новая численность превышает вместимость аудитории в расписании')
    if kind == 'rooms' and any(db.get(Group, x.group_id).size > data.capacity for x in future):
        raise HTTPException(409, 'Новая вместимость меньше численности назначенной группы')
    for k,v in data.model_dump().items():
        if k in model.__table__.columns:
            setattr(obj, k, v)
    db.flush()
    return directory_view(obj)

@app.get('/api/v1/users')
def users(user=Depends(admin), db=Depends(get_db)):
    if user.is_guest or guest_mode(): raise HTTPException(404)
    return [user_view(x) for x in db.scalars(select(User).order_by(User.id))]

@app.post('/api/v1/users', status_code=201)
def add_user(data: UserIn, user=Depends(admin), db=Depends(get_db)):
    if user.is_guest or guest_mode(): raise HTTPException(404)
    if data.group_id:
        require(db, Group, data.group_id)
    if data.teacher_id:
        require(db, Teacher, data.teacher_id)
    if data.role=='student' and not data.group_id or data.role=='teacher' and not data.teacher_id:
        raise HTTPException(422, 'Выберите группу студента или запись преподавателя')
    obj = User(**data.model_dump(exclude={'password'}), password_hash=password_hash(data.password))
    db.add(obj)
    db.flush()
    return user_view(obj)

@app.post('/api/v1/users/{ident}/toggle')
def toggle_user(ident: int, user=Depends(admin), db=Depends(get_db)):
    if user.is_guest or guest_mode(): raise HTTPException(404)
    if ident == user.id:
        raise HTTPException(422, 'Нельзя отключить собственную учётную запись')
    obj = require(db, User, ident)
    obj.active = not obj.active
    db.execute(delete(Session).where(Session.user_id==ident))
    return user_view(obj)

@app.get('/api/v1/periods')
def periods(user=Depends(current_user), db=Depends(get_db)):
    return [directory_view(x) for x in db.scalars(select(Period).order_by(Period.start.desc()))]

@app.post('/api/v1/periods', status_code=201)
def add_period(data: PeriodIn, user=Depends(editor), db=Depends(get_db)):
    obj=Period(**data.model_dump()); db.add(obj); db.flush()
    return directory_view(obj)

@app.get('/api/v1/schedules')
def schedules(user=Depends(current_user), db=Depends(get_db)):
    query=select(Schedule).order_by(Schedule.id.desc())
    if user.role not in ('admin','dispatcher'):
        query=query.where(Schedule.status=='published')
    return [directory_view(x) for x in db.scalars(query)]

@app.post('/api/v1/schedules', status_code=201)
def add_schedule(data: ScheduleIn, user=Depends(editor), db=Depends(get_db)):
    require(db, Period, data.period_id)
    obj=Schedule(**data.model_dump(), author_id=user.id); db.add(obj); db.flush()
    return directory_view(obj)

@app.post('/api/v1/schedules/{ident}/publish')
def publish(ident: int, user=Depends(editor), db=Depends(get_db)):
    lock_writes(db)
    obj=require(db, Schedule, ident)
    if not db.scalar(select(Lesson.id).where(Lesson.schedule_id==ident, Lesson.status!='cancelled').limit(1)):
        raise HTTPException(422, 'Нельзя опубликовать пустое расписание')
    if obj.status != 'published':
        obj.status='published'
        audit(db, user, 'published', schedule_id=ident)
    return directory_view(obj)

@app.get('/api/v1/lessons')
def lessons(start: date, end: date, group_id: int | None=None, teacher_id: int | None=None, room_id: int | None=None,
            schedule_id: int | None=None, offset: int=Query(0,ge=0), limit: int=Query(200,ge=1,le=500), user=Depends(current_user), db=Depends(get_db)):
    if end < start or (end-start).days > 92 or start.year < 2000 or end.year > 2100:
        raise HTTPException(422, 'Выберите диапазон не больше 93 дней')
    begin = datetime.combine(start, datetime.min.time(), MOSCOW)
    finish = datetime.combine(end+timedelta(days=1), datetime.min.time(), MOSCOW)
    query=select(Lesson).join(Schedule).where(Lesson.starts>=begin, Lesson.starts<finish)
    if user.role not in ('admin','dispatcher'):
        query=query.where(Schedule.status=='published')
    for key,value in [('group_id',group_id),('teacher_id',teacher_id),('room_id',room_id),('schedule_id',schedule_id)]:
        if value is not None:
            query=query.where(getattr(Lesson,key)==value)
    total=db.scalar(select(func.count()).select_from(query.subquery()))
    items=[]
    joined=query.add_columns(Group.name,Teacher.name,Room.name,Subject.name,Schedule.status).join(Group,Lesson.group_id==Group.id).join(Teacher,Lesson.teacher_id==Teacher.id).join(Room,Lesson.room_id==Room.id).join(Subject,Lesson.subject_id==Subject.id)
    for item, group, teacher, room, subject, schedule_status in db.execute(joined.order_by(Lesson.starts,Lesson.id).offset(offset).limit(limit)):
        values=snapshot(item)
        values.update(group=group,teacher=teacher,room=room,subject=subject,schedule_status=schedule_status)
        items.append(values)
    return {'items':items,'total':total,'offset':offset,'limit':limit}

@app.post('/api/v1/lessons', status_code=201)
def add_lesson(data: LessonIn, user=Depends(editor), db=Depends(get_db)):
    lock_writes(db)
    conflicts=validate_lesson(db,data)
    if conflicts:
        raise HTTPException(409, {'message':'Время уже занято','conflicts':conflicts})
    return snapshot(create_lesson(db,data,user))

@app.post('/api/v1/series/preview')
def preview_series(data: SeriesIn, user=Depends(editor), db=Depends(get_db)):
    rows=[]
    for item in expand_series(data):
        rows.append({'starts':item.starts.isoformat(),'ends':item.ends.isoformat(),'conflicts':validate_lesson(db,item)})
    return {'items':rows,'can_save':not any(x['conflicts'] for x in rows)}

@app.post('/api/v1/series', status_code=201)
def add_series(data: SeriesIn, user=Depends(editor), db=Depends(get_db)):
    lock_writes(db)
    digest=hashlib.sha256(json.dumps(data.model_dump(mode='json',exclude={'request_key'}),sort_keys=True).encode()).hexdigest()
    existing=db.scalar(select(Series).where(Series.author_id==user.id,Series.request_key==data.request_key))
    if existing:
        if existing.payload_hash != digest:
            raise HTTPException(409, 'Этот ключ запроса уже использован для другой серии')
        return {'series_id':existing.id,'lesson_ids':list(db.scalars(select(Lesson.id).where(Lesson.series_id==existing.id).order_by(Lesson.id))),'replayed':True}
    items=expand_series(data)
    conflicts=[]
    for item in items:
        conflicts.extend(validate_lesson(db,item))
    if conflicts:
        raise HTTPException(409, {'message':'Серия не сохранена: устраните пересечения','conflicts':conflicts})
    series=Series(request_key=data.request_key,author_id=user.id,payload_hash=digest)
    db.add(series); db.flush()
    ids=[create_lesson(db,item,user,series.id).id for item in items]
    return {'series_id':series.id,'lesson_ids':ids,'replayed':False}

@app.put('/api/v1/lessons/{ident}')
def change_lesson(ident: int, data: ChangeIn, user=Depends(editor), db=Depends(get_db)):
    lock_writes(db)
    item=require(db,Lesson,ident)
    if item.version != data.version:
        raise HTTPException(409, 'Занятие уже изменилось. Обновите список и повторите.')
    if item.status=='cancelled':
        raise HTTPException(409, 'Отменённое занятие нельзя переносить. Создайте новое.')
    if item.schedule_id != data.schedule_id:
        raise HTTPException(422, 'Перенос между расписаниями не поддерживается')
    conflicts=validate_lesson(db,data,exclude_id=ident)
    if conflicts:
        raise HTTPException(409, {'message':'Перенос невозможен: время занято','conflicts':conflicts})
    before=snapshot(item)
    for key,value in data.model_dump(exclude={'version'}).items():
        setattr(item,key,value)
    item.status='moved'; item.version+=1
    db.flush(); audit(db,user,'moved',item,before=before,reason=data.reason)
    return snapshot(item)

@app.post('/api/v1/lessons/{ident}/cancel')
def cancel_lesson(ident: int, data: CancelIn, user=Depends(editor), db=Depends(get_db)):
    lock_writes(db)
    item=require(db,Lesson,ident)
    if item.version != data.version:
        raise HTTPException(409, 'Занятие уже изменилось. Обновите список.')
    if item.status=='cancelled':
        raise HTTPException(409, 'Занятие уже отменено')
    before=snapshot(item)
    item.status='cancelled'; item.reason=data.reason; item.version+=1
    db.flush(); audit(db,user,'cancelled',item,before=before,reason=data.reason)
    return snapshot(item)

@app.get('/api/v1/lessons/{ident}/history')
def lesson_history(ident: int, user=Depends(current_user), db=Depends(get_db)):
    item=require(db,Lesson,ident)
    if user.role not in ('admin','dispatcher') and db.get(Schedule,item.schedule_id).status!='published':
        raise HTTPException(404, 'Занятие не найдено')
    return [{'id':a.id,'action':a.action,'reason':a.reason,'created':a.created,'before':a.before,'after':a.after,
             'actor':db.get(User,a.actor_id).name if user.role in ('admin','dispatcher') else 'Диспетчер'}
            for a in db.scalars(select(Audit).where(Audit.lesson_id==ident).order_by(Audit.id.desc()))]

dist=ROOT/'frontend'/'dist'
if dist.exists():
    app.mount('/assets',StaticFiles(directory=dist/'assets'),name='assets')
    @app.get('/')
    def index():
        return FileResponse(dist/'index.html')
