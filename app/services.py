from datetime import timedelta
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from sqlalchemy import select, text, or_
from .models import Group, Teacher, Room, Subject, Period, Schedule, Lesson, Audit

MOSCOW = ZoneInfo('Europe/Moscow')
DIRECTORIES = {'groups': Group, 'teachers': Teacher, 'rooms': Room, 'subjects': Subject}

def lock_writes(db):
    # Serialize one workspace, but never queue indefinitely behind a stalled writer.
    db.execute(text("SET LOCAL lock_timeout = '2s'"))
    db.execute(text('SELECT pg_advisory_xact_lock(7322026, :workspace)'), {'workspace':db.info.get('workspace_id',1)})

def require(db, model, ident):
    obj = db.get(model, ident)
    if obj is None or (hasattr(model, 'workspace_id') and obj.workspace_id != db.info.get('workspace_id',1)):
        raise HTTPException(404, 'Запись не найдена')
    return obj

def snapshot(lesson):
    return {key: (getattr(lesson, key).isoformat() if key in ('starts', 'ends') else getattr(lesson, key))
            for key in ('id','schedule_id','group_id','teacher_id','room_id','subject_id','series_id','starts','ends','status','reason','version')}

def audit(db, user, action, lesson=None, schedule_id=None, before=None, reason=''):
    db.add(Audit(actor_id=user.id, action=action, lesson_id=lesson.id if lesson else None,
                 schedule_id=lesson.schedule_id if lesson else schedule_id,
                 before=before or {}, after=snapshot(lesson) if lesson else {}, reason=reason))

def validate_lesson(db, data, exclude_id=None):
    schedule = require(db, Schedule, data.schedule_id)
    period = require(db, Period, schedule.period_id)
    start, end = data.starts.astimezone(MOSCOW), data.ends.astimezone(MOSCOW)
    if start.date() != end.date():
        raise HTTPException(422, 'Занятие должно начинаться и заканчиваться в один день по Москве')
    if not period.start <= start.date() <= period.end:
        raise HTTPException(422, 'Дата занятия вне учебного периода')
    refs = []
    for model, key in ((Group,'group_id'),(Teacher,'teacher_id'),(Room,'room_id'),(Subject,'subject_id')):
        obj = require(db, model, getattr(data, key))
        if not obj.active:
            raise HTTPException(422, f'Запись «{obj.name}» находится в архиве')
        refs.append(obj)
    if refs[0].size > refs[2].capacity:
        raise HTTPException(422, f'В аудитории {refs[2].name} мест: {refs[2].capacity}, в группе: {refs[0].size}')
    query = select(Lesson).where(Lesson.status != 'cancelled', Lesson.starts < data.ends, Lesson.ends > data.starts,
                               or_(Lesson.group_id == data.group_id, Lesson.teacher_id == data.teacher_id, Lesson.room_id == data.room_id))
    if exclude_id:
        query = query.where(Lesson.id != exclude_id)
    conflicts = []
    for lesson in db.scalars(query.order_by(Lesson.starts, Lesson.id)):
        types = [label for key, label in [('group_id','Группа'),('teacher_id','Преподаватель'),('room_id','Аудитория')]
                 if getattr(data, key) == getattr(lesson, key)]
        conflicts.append({'lesson_id':lesson.id, 'starts':lesson.starts.isoformat(), 'ends':lesson.ends.isoformat(), 'resources':types})
    return conflicts

def expand_series(data):
    current = data.starts.astimezone(MOSCOW)
    ending = data.ends.astimezone(MOSCOW)
    if data.until < current.date() or (data.until-current.date()).days > 366:
        raise HTTPException(422, 'Диапазон повторения должен быть от даты занятия до года')
    values = []
    while current.date() <= data.until:
        values.append(data.model_copy(update={'starts':current, 'ends':ending}))
        current += timedelta(weeks=data.interval_weeks)
        ending += timedelta(weeks=data.interval_weeks)
    return values

def create_lesson(db, data, user, series_id=None):
    lesson = Lesson(**{key:getattr(data,key) for key in ('schedule_id','group_id','teacher_id','room_id','subject_id','starts','ends')}, series_id=series_id)
    db.add(lesson)
    db.flush()
    audit(db, user, 'created', lesson)
    return lesson
