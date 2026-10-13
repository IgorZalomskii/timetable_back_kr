from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from .errors import Validation

MOSCOW = ZoneInfo('Europe/Moscow')
LESSON_FIELDS = ('id','schedule_id','group_id','teacher_id','room_id','subject_id','series_id','starts','ends','status','reason','version')

def snapshot(lesson):
    return {key: lesson[key].isoformat() if key in ('starts','ends') else lesson[key] for key in LESSON_FIELDS}

def validate_lesson(data, period, refs):
    start, end = data.starts.astimezone(MOSCOW), data.ends.astimezone(MOSCOW)
    if start.date() != end.date():
        raise Validation('Занятие должно начинаться и заканчиваться в один день по Москве')
    if not period['start'] <= start.date() <= period['end']:
        raise Validation('Дата занятия вне учебного периода')
    for obj in refs:
        if not obj['active']:
            raise Validation(f"Запись «{obj['name']}» находится в архиве")
    group, _, room, _ = refs
    if group['size'] > room['capacity']:
        raise Validation(f"В аудитории {room['name']} мест: {room['capacity']}, в группе: {group['size']}")

def date_range(start, end):
    if end < start or (end-start).days > 92 or start.year < 2000 or end.year > 2100:
        raise Validation('Выберите диапазон не больше 93 дней')
    return datetime.combine(start, datetime.min.time(), MOSCOW), datetime.combine(end+timedelta(days=1), datetime.min.time(), MOSCOW)
