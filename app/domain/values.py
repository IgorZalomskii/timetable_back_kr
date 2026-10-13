from dataclasses import dataclass
from datetime import datetime

@dataclass(frozen=True)
class RequestContext:
    workspace_id: int
    user_id: int
    role: str
    is_guest: bool = False
    correlation_id: str = ''

    @property
    def can_edit(self): return self.role in ('admin', 'dispatcher')

@dataclass(frozen=True)
class SystemContext:
    """Explicit authority for authentication and expiring-demo maintenance."""
    purpose: str

@dataclass(frozen=True)
class LessonCommand:
    schedule_id: int
    group_id: int
    teacher_id: int
    room_id: int
    subject_id: int
    starts: datetime
    ends: datetime
