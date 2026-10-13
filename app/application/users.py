from dataclasses import asdict
from app.domain.errors import NotFound, Validation
from .common import admin, user_view

def access(services, context):
    admin(context)
    if context.is_guest or services.guest_mode: raise NotFound('Not Found')

class ListUsers:
    def __init__(self, services): self.services = services
    def execute(self, context):
        access(self.services, context)
        with self.services.uow(context) as uow: return [user_view(x) for x in uow.catalog.list_users(context)]

class CreateUser:
    def __init__(self, services): self.services = services
    def execute(self, context, data):
        access(self.services, context)
        with self.services.transaction(context, 'user_create', guard=admin) as uow:
            if data.group_id: uow.catalog.get_directory(context, 'groups', data.group_id)
            if data.teacher_id: uow.catalog.get_directory(context, 'teachers', data.teacher_id)
            if data.role == 'student' and not data.group_id or data.role == 'teacher' and not data.teacher_id: raise Validation('Выберите группу студента или запись преподавателя')
            values = asdict(data); values.pop('password')
            result = user_view(uow.catalog.create_user(context, values | {'password_hash':self.services.passwords.hash(data.password)}))
        return result

class ToggleUser:
    def __init__(self, services): self.services = services
    def execute(self, context, ident):
        access(self.services, context)
        if ident == context.user_id: raise Validation('Нельзя отключить собственную учётную запись')
        with self.services.transaction(context, 'user_toggle', guard=admin) as uow: result = user_view(uow.catalog.toggle_user(context, ident))
        return result
