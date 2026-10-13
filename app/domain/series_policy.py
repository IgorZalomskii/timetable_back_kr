from dataclasses import asdict, replace
from datetime import timedelta
import hashlib
import json
from .lesson_policy import MOSCOW
from .errors import Validation

def expand_series(data):
    current, ending = data.starts.astimezone(MOSCOW), data.ends.astimezone(MOSCOW)
    if data.until < current.date() or (data.until-current.date()).days > 366:
        raise Validation('Диапазон повторения должен быть от даты занятия до года')
    values = []
    while current.date() <= data.until:
        values.append(replace(data, starts=current, ends=ending))
        current += timedelta(weeks=data.interval_weeks)
        ending += timedelta(weeks=data.interval_weeks)
    return values

def payload_hash(data):
    # Match the pre-refactor Pydantic JSON representation, including UTC's Z.
    def encode(value):
        result = value.isoformat()
        return result[:-6]+'Z' if result.endswith('+00:00') else result
    values = asdict(data)
    values.pop('request_key')
    return hashlib.sha256(json.dumps(values, sort_keys=True, default=encode).encode()).hexdigest()
