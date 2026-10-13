"""Private, expiring coursework examples. No shared demo accounts or credentials."""
import secrets
from datetime import datetime, timedelta, timezone, time
from sqlalchemy import select, func, delete, text
from fastapi import HTTPException
from .models import Workspace, User, Session, LoginAttempt, Group, Teacher, Room, Subject, Period, Schedule, Lesson
from .security import token_hash
from .services import MOSCOW, audit, snapshot

LIFETIME = timedelta(days=7)
MAX_WORKSPACES = 1000

def cleanup(db, now=None):
    now = now or datetime.now(timezone.utc)
    result = db.execute(delete(Workspace).where(Workspace.kind=='demo', Workspace.expires<=now))
    db.execute(delete(LoginAttempt).where(LoginAttempt.created < now-timedelta(minutes=15)))
    return result.rowcount

def reserve_creation(db, request, replacing=None):
    db.execute(text('SELECT pg_advisory_xact_lock(7322028)'))
    now = datetime.now(timezone.utc)
    cleanup(db, now)
    key = token_hash('guest:'+ (request.client.host if request.client else 'unknown'))
    if db.scalar(select(func.count()).select_from(LoginAttempt).where(LoginAttempt.key==key)) >= 10:
        raise HTTPException(429, 'Слишком много новых демонстраций. Попробуйте через 15 минут.')
    count_query=select(func.count()).select_from(Workspace).where(Workspace.kind=='demo')
    if replacing is not None:
        count_query=count_query.where(Workspace.id!=replacing)
    if db.scalar(count_query) >= MAX_WORKSPACES:
        raise HTTPException(503, 'Сейчас открыто много демонстраций. Попробуйте позже.')
    db.add(LoginAttempt(key=key))

def seed_workspace(db, role='student'):
    now = datetime.now(timezone.utc)
    workspace = Workspace(kind='demo', expires=now+LIFETIME)
    db.add(workspace); db.flush()
    db.info['workspace_id'] = workspace.id
    groups = [Group(name='ИКБО-15-23',size=24),Group(name='ИКБО-14-23',size=22)]
    teachers = [Teacher(name=n) for n in ('Анна Смирнова','Михаил Орлов','Елена Соколова')]
    rooms = [Room(name='А-301',capacity=30),Room(name='Б-204',capacity=28),Room(name='Лаборатория 105',capacity=26)]
    subjects = [Subject(name=n) for n in ('Бэкенд-разработка','Базы данных','Веб-технологии','Проектирование систем')]
    db.add_all(groups+teachers+rooms+subjects); db.flush()
    user = User(username='guest_'+secrets.token_hex(16), password_hash='!', name='Гость',
        role=role,is_guest=True,group_id=groups[0].id if role=='student' else None,
        teacher_id=teachers[0].id if role=='teacher' else None)
    db.add(user); db.flush()
    today = now.astimezone(MOSCOW).date()
    monday = today-timedelta(days=today.weekday())
    period = Period(name='Учебный семестр',start=monday-timedelta(days=7),end=monday+timedelta(days=90))
    db.add(period); db.flush()
    published = Schedule(name='Основное расписание',period_id=period.id,author_id=user.id,status='published')
    draft = Schedule(name='Подготовка следующей недели',period_id=period.id,author_id=user.id)
    db.add_all([published,draft]); db.flush()
    seeded=[]
    for week in range(2):
        for day in range(5):
            for slot in range(2):
                for group_index in range(2):
                    starts=datetime.combine(monday+timedelta(days=week*7+day),time(9+slot*2),MOSCOW)
                    teacher_index=(day+slot+group_index)%3
                    item=Lesson(schedule_id=published.id,group_id=groups[group_index].id,
                        teacher_id=teachers[teacher_index].id,room_id=rooms[teacher_index].id,
                        subject_id=subjects[(day+slot)%4].id,starts=starts,ends=starts+timedelta(minutes=90))
                    db.add(item); db.flush(); audit(db,user,'created',item)
                    seeded.append(item)
    moved=seeded[4]; before=snapshot(moved)
    moved.starts+=timedelta(hours=6); moved.ends+=timedelta(hours=6)
    moved.status='moved'; moved.reason='Аудитория занята мероприятием'; moved.version=2
    db.flush(); audit(db,user,'moved',moved,before=before,reason=moved.reason)
    cancelled=seeded[8]; before=snapshot(cancelled)
    cancelled.status='cancelled'; cancelled.reason='Самостоятельная работа по теме'; cancelled.version=2
    db.flush(); audit(db,user,'cancelled',cancelled,before=before,reason=cancelled.reason)
    starts=datetime.combine(monday+timedelta(days=7),time(15),MOSCOW)
    pending=Lesson(schedule_id=draft.id,group_id=groups[0].id,teacher_id=teachers[0].id,room_id=rooms[0].id,
        subject_id=subjects[0].id,starts=starts,ends=starts+timedelta(minutes=90))
    db.add(pending); db.flush(); audit(db,user,'created',pending)
    return workspace,user

def make_session(db, user, workspace):
    raw,csrf=secrets.token_urlsafe(32),secrets.token_urlsafe(32)
    session=Session(token_hash=token_hash(raw),user_id=user.id,csrf=csrf,expires=workspace.expires)
    db.add(session); db.flush()
    return raw,session
