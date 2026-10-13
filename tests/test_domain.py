from datetime import date, datetime
from dataclasses import replace
import pytest
from app.domain.values import LessonCommand
from app.application.dto import SeriesCommand
from app.domain.lesson_policy import validate_lesson, date_range, snapshot
from app.domain.series_policy import expand_series, payload_hash
from app.domain.errors import Validation

def command():
    return LessonCommand(1,1,1,1,1,datetime.fromisoformat('2026-10-05T09:00:00+03:00'),datetime.fromisoformat('2026-10-05T10:30:00+03:00'))

def refs(): return [{'active':True,'name':'Group','size':25},{'active':True,'name':'Teacher'},{'active':True,'name':'Room','capacity':30},{'active':True,'name':'Subject'}]

def test_lesson_policy_checks_moscow_day_period_capacity_archive():
    period = {'start':date(2026,9,1),'end':date(2026,12,31)}
    validate_lesson(command(),period,refs())
    with pytest.raises(Validation,match='один день'): validate_lesson(replace(command(),starts=datetime.fromisoformat('2026-10-04T20:30:00Z')),period,refs())
    with pytest.raises(Validation,match='периода'): validate_lesson(command(),{'start':date(2027,1,1),'end':date(2027,2,1)},refs())
    small = refs(); small[2]['capacity']=20
    with pytest.raises(Validation,match='мест'): validate_lesson(command(),period,small)
    archived = refs(); archived[3]['active']=False
    with pytest.raises(Validation,match='архиве'): validate_lesson(command(),period,archived)

def test_recurring_policy_and_canonical_hash_match_legacy_schema():
    from dataclasses import asdict
    import hashlib,json
    from app.schemas import SeriesIn
    data = SeriesCommand(**asdict(command()),until=date(2026,11,2),request_key='test-series',interval_weeks=2)
    assert [x.starts.day for x in expand_series(data)] == [5,19,2]
    assert payload_hash(data) == payload_hash(replace(data,request_key='another-key'))
    assert payload_hash(data) != payload_hash(replace(data,interval_weeks=1))
    for value in (data,replace(data,starts=datetime.fromisoformat('2026-10-05T06:00:00Z'),ends=datetime.fromisoformat('2026-10-05T07:30:00Z'))):
        legacy=SeriesIn(**asdict(value)).model_dump(mode='json',exclude={'request_key'})
        assert payload_hash(value) == hashlib.sha256(json.dumps(legacy,sort_keys=True).encode()).hexdigest()

def test_date_range_rejects_extreme_and_large_dates_before_arithmetic():
    for start,end in [(date.max,date.max),(date(2026,1,1),date(2026,12,1))]:
        with pytest.raises(Validation): date_range(start,end)
