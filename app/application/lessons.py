from dataclasses import asdict
from app.domain.errors import Conflict, Validation, NotFound
from app.domain.lesson_policy import snapshot, validate_lesson, date_range
from .common import editor

def validate(uow, context, data, exclude_id=None):
    schedule = uow.schedules.get_schedule(context, data.schedule_id)
    period = uow.catalog.get_period(context, schedule['period_id'])
    refs = [uow.catalog.get_directory(context, kind, getattr(data, field)) for kind,field in [('groups','group_id'),('teachers','teacher_id'),('rooms','room_id'),('subjects','subject_id')]]
    validate_lesson(data, period, refs)
    return uow.schedules.conflicts(context, data, exclude_id)

def create(uow, context, data, series_id=None):
    values = {key:getattr(data,key) for key in ('schedule_id','group_id','teacher_id','room_id','subject_id','starts','ends')}
    lesson = uow.schedules.insert_lesson(context, values | {'series_id':series_id})
    uow.schedules.append_audit(context, 'created', lesson)
    return lesson

class ListLessons:
    def __init__(self, services): self.services = services
    def execute(self, context, start, end, filters, offset=0, limit=200):
        begin, finish = date_range(start, end)
        with self.services.uow(context) as uow:
            return uow.schedules.list_lessons(context, begin, finish, filters, offset, limit)

class CreateLesson:
    def __init__(self, services): self.services = services
    def execute(self, context, data):
        editor(context)
        with self.services.transaction(context, 'lesson_create', guard=editor) as uow:
            conflicts = validate(uow, context, data)
            if conflicts: raise Conflict({'message':'Время уже занято','conflicts':conflicts})
            result = snapshot(create(uow, context, data))
        return result

class MoveLesson:
    def __init__(self, services): self.services = services
    def execute(self, context, ident, data):
        editor(context)
        with self.services.transaction(context, 'lesson_move', guard=editor) as uow:
            item = uow.schedules.get_lesson(context, ident)
            if item['version'] != data.version: raise Conflict('Занятие уже изменилось. Обновите список и повторите.')
            if item['status'] == 'cancelled': raise Conflict('Отменённое занятие нельзя переносить. Создайте новое.')
            if item['schedule_id'] != data.schedule_id: raise Validation('Перенос между расписаниями не поддерживается')
            conflicts = validate(uow, context, data, ident)
            if conflicts: raise Conflict({'message':'Перенос невозможен: время занято','conflicts':conflicts})
            before = snapshot(item)
            values = asdict(data) | {'status':'moved','version':item['version']+1}
            item = uow.schedules.update_lesson(context, ident, values)
            uow.schedules.append_audit(context, 'moved', item, before=before, reason=data.reason)
            result = snapshot(item)
        return result

class CancelLesson:
    def __init__(self, services): self.services = services
    def execute(self, context, ident, data):
        editor(context)
        with self.services.transaction(context, 'lesson_cancel', guard=editor) as uow:
            item = uow.schedules.get_lesson(context, ident)
            if item['version'] != data.version: raise Conflict('Занятие уже изменилось. Обновите список.')
            if item['status'] == 'cancelled': raise Conflict('Занятие уже отменено')
            before = snapshot(item)
            item = uow.schedules.update_lesson(context, ident, {'status':'cancelled','reason':data.reason,'version':item['version']+1})
            uow.schedules.append_audit(context, 'cancelled', item, before=before, reason=data.reason)
            result = snapshot(item)
        return result

class GetHistory:
    def __init__(self, services): self.services = services
    def execute(self, context, ident):
        with self.services.uow(context) as uow:
            item = uow.schedules.get_lesson(context, ident)
            schedule = uow.schedules.get_schedule(context, item['schedule_id'])
            if not context.can_edit and schedule['status'] != 'published': raise NotFound('Занятие не найдено')
            return uow.schedules.history(context, ident)
