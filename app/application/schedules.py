from dataclasses import asdict
from app.domain.errors import Validation
from .common import editor

class ListSchedules:
    def __init__(self, services): self.services = services
    def execute(self, context):
        with self.services.uow(context) as uow: return uow.schedules.list_schedules(context)

class CreateSchedule:
    def __init__(self, services): self.services = services
    def execute(self, context, data):
        editor(context)
        with self.services.transaction(context, 'schedule_create', guard=editor) as uow:
            uow.catalog.get_period(context, data.period_id)
            result = uow.schedules.create_schedule(context, asdict(data) | {'author_id':context.user_id})
        return result

class PublishSchedule:
    def __init__(self, services): self.services = services
    def execute(self, context, ident):
        editor(context)
        with self.services.transaction(context, 'schedule_publish', guard=editor) as uow:
            result = uow.schedules.get_schedule(context, ident)
            if not uow.schedules.has_lessons(context, ident): raise Validation('Нельзя опубликовать пустое расписание')
            if result['status'] != 'published':
                result = uow.schedules.publish_schedule(context, ident)
                uow.schedules.append_audit(context, 'published', schedule_id=ident)
        return result
