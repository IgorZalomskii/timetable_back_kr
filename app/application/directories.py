from dataclasses import asdict
from app.domain.errors import NotFound, Conflict
from .common import admin

def directory_kind(kind):
    if kind not in ('groups','teachers','rooms','subjects'): raise NotFound('Справочник не найден')

class ListDirectory:
    def __init__(self, services): self.services = services
    def execute(self, context, kind):
        directory_kind(kind)
        with self.services.uow(context) as uow: return uow.catalog.list_directory(context, kind)

class CreateDirectoryEntry:
    def __init__(self, services): self.services = services
    def execute(self, context, kind, data):
        admin(context); directory_kind(kind)
        with self.services.transaction(context, 'directory_create', guard=admin) as uow:
            result = uow.catalog.create_directory(context, kind, asdict(data))
        return result

class UpdateDirectoryEntry:
    def __init__(self, services): self.services = services
    def execute(self, context, kind, ident, data):
        admin(context); directory_kind(kind)
        with self.services.transaction(context, 'directory_update', guard=admin) as uow:
            uow.catalog.get_directory(context, kind, ident)
            future = uow.catalog.future_resources(context, kind, ident, self.services.clock.now())
            if future and not data.active: raise Conflict('Сначала перенесите или отмените будущие занятия этой записи')
            if kind == 'groups' and any(row['capacity'] < data.size for row in future): raise Conflict('Новая численность превышает вместимость аудитории в расписании')
            if kind == 'rooms' and any(row['size'] > data.capacity for row in future): raise Conflict('Новая вместимость меньше численности назначенной группы')
            result = uow.catalog.update_directory(context, kind, ident, asdict(data))
        return result
