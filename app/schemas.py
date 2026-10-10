from datetime import date, datetime
from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator

class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=128)

class GuestIn(BaseModel):
    role: Literal['admin', 'dispatcher', 'teacher', 'student'] = 'student'

class ProfileIn(BaseModel):
    role: Literal['admin', 'dispatcher', 'teacher', 'student']
    name: str | None = Field(default=None, min_length=1, max_length=80)
    group_id: int | None = Field(default=None, gt=0)
    teacher_id: int | None = Field(default=None, gt=0)
    @field_validator('name')
    @classmethod
    def clean_name(cls, value):
        if value is not None and not value.strip():
            raise ValueError('Введите имя')
        return value.strip() if value is not None else None

class DirectoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    size: int = Field(default=20, ge=1, le=1000)
    capacity: int = Field(default=30, ge=1, le=1000)
    active: bool = True
    @field_validator('name')
    @classmethod
    def name_not_blank(cls, value):
        if not value.strip():
            raise ValueError('Название не может быть пустым')
        return value.strip()

class UserIn(BaseModel):
    username: str = Field(pattern=r'^[a-zA-Z0-9_.-]{3,80}$')
    name: str = Field(min_length=1, max_length=150)
    password: str = Field(min_length=10, max_length=128)
    role: Literal['admin', 'dispatcher', 'teacher', 'student']
    group_id: int | None = None
    teacher_id: int | None = None

class PeriodIn(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    start: date
    end: date
    @model_validator(mode='after')
    def dates(self):
        if self.end < self.start or (self.end - self.start).days > 366:
            raise ValueError('Период должен длиться от 1 до 367 дней')
        return self

class ScheduleIn(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    period_id: int

class LessonIn(BaseModel):
    schedule_id: int
    group_id: int
    teacher_id: int
    room_id: int
    subject_id: int
    starts: datetime
    ends: datetime
    @model_validator(mode='after')
    def times(self):
        if self.starts.tzinfo is None or self.ends.tzinfo is None:
            raise ValueError('Время должно содержать часовой пояс')
        if self.ends <= self.starts or (self.ends-self.starts).total_seconds() > 12*3600:
            raise ValueError('Продолжительность занятия должна быть от 1 секунды до 12 часов')
        return self

class SeriesIn(LessonIn):
    until: date
    interval_weeks: Literal[1, 2] = 1
    request_key: str = Field(min_length=8, max_length=100)

class ChangeIn(LessonIn):
    reason: str = Field(min_length=3, max_length=500)
    version: int = Field(ge=1)

class CancelIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)
    version: int = Field(ge=1)
