"""Explicit local demo setup; never run automatically on server startup."""
import os
from datetime import datetime, timedelta
from sqlalchemy import select
from .db import SessionLocal
from .models import Group, Teacher, Room, Subject, User, Period, Schedule
from .schemas import LessonIn
from .security import password_hash
from .domain.lesson_policy import MOSCOW
from .domain.values import RequestContext
from .application.lessons import create
from .adapters.db.uow import SqlUnitOfWork

def seed():
    if os.environ.get('APP_ENV') == 'production':
        raise SystemExit('Demo seed is disabled in production. Create an administrator with app.admin.')
    with SessionLocal.begin() as db:
        db.info['workspace_id']=1
        if db.scalar(select(User.id).limit(1)):
            print('Demo already exists; nothing changed'); return
        groups=[Group(name='ИКБО-15-23',size=24),Group(name='ИКБО-14-23',size=26)]
        teachers=[Teacher(name='Андрей Рачков'),Teacher(name='Мария Соколова'),Teacher(name='Илья Волков')]
        rooms=[Room(name='А-301',capacity=30),Room(name='Б-204',capacity=28),Room(name='Лаборатория 12',capacity=25)]
        subjects=[Subject(name='Бэкенд-разработка'),Subject(name='Базы данных'),Subject(name='Проектирование систем')]
        db.add_all(groups+teachers+rooms+subjects); db.flush()
        for login,role,name,group_id,teacher_id in [('admin','admin','Администратор',None,None),('dispatcher','dispatcher','Диспетчер',None,None),('student','student','Студент',groups[0].id,None),('teacher','teacher','Андрей Рачков',None,teachers[0].id)]:
            db.add(User(username=login,role=role,name=name,password_hash=password_hash('Schedule-demo-2026!'),group_id=group_id,teacher_id=teacher_id))
        db.flush()
        admin=db.scalar(select(User).where(User.username=='admin'))
        context=RequestContext(1,admin.id,admin.role)
        uow=SqlUnitOfWork(db,context)
        today=datetime.now(MOSCOW).date()
        monday=today-timedelta(days=today.weekday())
        period=Period(name=f'Учебный период {today.year}',start=monday-timedelta(days=14),end=monday+timedelta(days=120))
        db.add(period); db.flush()
        schedule=Schedule(name='Основное расписание',period_id=period.id,status='published',author_id=admin.id)
        draft=Schedule(name='Дополнительные занятия',period_id=period.id,author_id=admin.id)
        db.add_all([schedule,draft]); db.flush()
        for week in range(3):
            for day in range(5):
                for slot in range(2):
                    idx=(day+slot)%3
                    start=datetime.combine(monday+timedelta(weeks=week,days=day),datetime.min.time(),MOSCOW)+timedelta(hours=9+slot*2)
                    create(uow,context,LessonIn(schedule_id=schedule.id,group_id=groups[0].id,teacher_id=teachers[idx].id,room_id=rooms[idx].id,subject_id=subjects[idx].id,starts=start,ends=start+timedelta(minutes=90)))
        print('Local legacy fixtures created. Public guest mode does not use these password accounts.')

if __name__=='__main__':
    seed()
