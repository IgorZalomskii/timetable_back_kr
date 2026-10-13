from datetime import date, datetime
from sqlalchemy import String, ForeignKey, ForeignKeyConstraint, CheckConstraint, UniqueConstraint, DateTime, JSON, func, text
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base

class Workspace(Base):
    __tablename__ = 'workspaces'
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), default='demo')
    created: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    __table_args__ = (CheckConstraint("kind IN ('legacy','demo')"),)

class Scoped:
    workspace_id: Mapped[int] = mapped_column(ForeignKey('workspaces.id', ondelete='CASCADE'), index=True)

def owned(*constraints):
    return (UniqueConstraint('workspace_id', 'id'), *constraints)

def local_fk(column, table):
    return ForeignKeyConstraint(['workspace_id', column], [f'{table}.workspace_id', f'{table}.id'])

class Group(Scoped, Base):
    __tablename__ = 'groups'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    size: Mapped[int] = mapped_column(default=20)
    active: Mapped[bool] = mapped_column(default=True)
    __table_args__ = owned(CheckConstraint('size > 0'), UniqueConstraint('workspace_id', 'name'))

class Teacher(Scoped, Base):
    __tablename__ = 'teachers'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    active: Mapped[bool] = mapped_column(default=True)
    __table_args__ = owned(UniqueConstraint('workspace_id', 'name'))

class Subject(Scoped, Base):
    __tablename__ = 'subjects'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    active: Mapped[bool] = mapped_column(default=True)
    __table_args__ = owned(UniqueConstraint('workspace_id', 'name'))

class Room(Scoped, Base):
    __tablename__ = 'rooms'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    capacity: Mapped[int] = mapped_column(default=30)
    active: Mapped[bool] = mapped_column(default=True)
    __table_args__ = owned(CheckConstraint('capacity > 0'), UniqueConstraint('workspace_id', 'name'))

class User(Scoped, Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(150))
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(20))
    active: Mapped[bool] = mapped_column(default=True)
    group_id: Mapped[int | None] = mapped_column()
    teacher_id: Mapped[int | None] = mapped_column()
    is_guest: Mapped[bool] = mapped_column(default=False, server_default='false')
    __table_args__ = owned(CheckConstraint("role IN ('admin','dispatcher','teacher','student')"), local_fk('group_id', 'groups'), local_fk('teacher_id', 'teachers'))

class Session(Base):
    __tablename__ = 'sessions'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'))
    csrf: Mapped[str] = mapped_column(String(80))
    expires: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class LoginAttempt(Base):
    __tablename__ = 'login_attempts'
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(64), index=True)
    created: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

class Period(Scoped, Base):
    __tablename__ = 'periods'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    start: Mapped[date]
    end: Mapped[date]
    __table_args__ = owned(CheckConstraint('"end" >= start'))

class Schedule(Scoped, Base):
    __tablename__ = 'schedules'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    period_id: Mapped[int] = mapped_column()
    status: Mapped[str] = mapped_column(String(20), default='draft')
    author_id: Mapped[int] = mapped_column()
    __table_args__ = owned(CheckConstraint("status IN ('draft','published')"), local_fk('period_id', 'periods'), local_fk('author_id', 'users'))

class Series(Scoped, Base):
    __tablename__ = 'series'
    id: Mapped[int] = mapped_column(primary_key=True)
    request_key: Mapped[str] = mapped_column(String(100))
    author_id: Mapped[int] = mapped_column()
    payload_hash: Mapped[str] = mapped_column(String(64))
    __table_args__ = owned(UniqueConstraint('author_id', 'request_key'), local_fk('author_id', 'users'))

class Lesson(Scoped, Base):
    __tablename__ = 'lessons'
    id: Mapped[int] = mapped_column(primary_key=True)
    schedule_id: Mapped[int] = mapped_column(index=True)
    group_id: Mapped[int] = mapped_column(index=True)
    teacher_id: Mapped[int] = mapped_column(index=True)
    room_id: Mapped[int] = mapped_column(index=True)
    subject_id: Mapped[int] = mapped_column()
    series_id: Mapped[int | None] = mapped_column()
    starts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default='planned')
    reason: Mapped[str] = mapped_column(String(500), default='')
    version: Mapped[int] = mapped_column(default=1)
    __table_args__ = owned(
        *[local_fk(column, table) for column, table in [('schedule_id','schedules'), ('group_id','groups'), ('teacher_id','teachers'), ('room_id','rooms'), ('subject_id','subjects'), ('series_id','series')]],
        CheckConstraint('ends > starts'),
        CheckConstraint("status IN ('planned','moved','cancelled')"),
        *[ExcludeConstraint((column, '='), (text("tstzrange(starts, ends, '[)')"), '&&'),
            where=text("status <> 'cancelled'"), using='gist', name=f'no_overlap_{column}')
          for column in ('group_id', 'teacher_id', 'room_id')],
    )

class Audit(Scoped, Base):
    __tablename__ = 'audit'
    id: Mapped[int] = mapped_column(primary_key=True)
    lesson_id: Mapped[int | None] = mapped_column(index=True)
    schedule_id: Mapped[int] = mapped_column()
    actor_id: Mapped[int] = mapped_column()
    action: Mapped[str] = mapped_column(String(40))
    reason: Mapped[str] = mapped_column(String(500), default='')
    before: Mapped[dict] = mapped_column(JSON, default=dict)
    after: Mapped[dict] = mapped_column(JSON, default=dict)
    created: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = owned(local_fk('lesson_id','lessons'), local_fk('schedule_id','schedules'), local_fk('actor_id','users'))
