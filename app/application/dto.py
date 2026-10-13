from dataclasses import dataclass
from datetime import date
from app.domain.values import LessonCommand, RequestContext

@dataclass(frozen=True)
class DirectoryCommand:
    name: str
    size: int = 20
    capacity: int = 30
    active: bool = True

@dataclass(frozen=True)
class UserCommand:
    username: str
    name: str
    password: str
    role: str
    group_id: int | None = None
    teacher_id: int | None = None

@dataclass(frozen=True)
class ProfileCommand:
    role: str
    name: str | None = None
    group_id: int | None = None
    teacher_id: int | None = None

@dataclass(frozen=True)
class PeriodCommand:
    name: str
    start: date
    end: date

@dataclass(frozen=True)
class ScheduleCommand:
    name: str
    period_id: int

@dataclass(frozen=True)
class SeriesCommand(LessonCommand):
    until: date
    request_key: str
    interval_weeks: int = 1

@dataclass(frozen=True)
class MoveCommand(LessonCommand):
    reason: str
    version: int

@dataclass(frozen=True)
class CancelCommand:
    reason: str
    version: int

@dataclass(frozen=True)
class Principal:
    context: RequestContext
    user: dict
    session: dict
    workspace: dict

@dataclass(frozen=True)
class SessionResult:
    body: dict
    raw_token: str | None = None
    max_age: int | None = None
