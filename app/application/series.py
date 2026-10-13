from app.domain.series_policy import expand_series, payload_hash
from app.domain.lesson_policy import snapshot
from app.domain.errors import Conflict
from .common import editor
from .lessons import validate, create

class PreviewSeries:
    def __init__(self, services): self.services = services
    def execute(self, context, data):
        editor(context)
        with self.services.uow(context) as uow:
            rows = [{'starts':item.starts.isoformat(),'ends':item.ends.isoformat(),'conflicts':validate(uow, context, item)} for item in expand_series(data)]
            return {'items':rows,'can_save':not any(row['conflicts'] for row in rows)}

class CreateSeries:
    def __init__(self, services): self.services = services
    def execute(self, context, data):
        editor(context)
        with self.services.transaction(context, 'series_create', guard=editor) as uow:
            digest = payload_hash(data)
            existing = uow.schedules.find_series(context, data.request_key)
            if existing:
                if existing['payload_hash'] != digest: raise Conflict('Этот ключ запроса уже использован для другой серии')
                result = {'series_id':existing['id'],'lesson_ids':uow.schedules.series_lessons(context, existing['id']),'replayed':True}
            else:
                items = expand_series(data)
                conflicts = [conflict for item in items for conflict in validate(uow, context, item)]
                if conflicts: raise Conflict({'message':'Серия не сохранена: устраните пересечения','conflicts':conflicts})
                series = uow.schedules.create_series(context, data.request_key, digest)
                ids = [create(uow, context, item, series['id'])['id'] for item in items]
                result = {'series_id':series['id'],'lesson_ids':ids,'replayed':False}
        return result
