from datetime import timedelta
import logging
import time
from app.domain.values import RequestContext, SystemContext
from app.domain.errors import Unauthorized, Forbidden, NotFound, Validation
from .dto import Principal, SessionResult
from .common import bucket, session_view, user_view

AUTH = SystemContext('authentication')

def principal(identity, services, correlation_id=''):
    now = services.clock.now()
    if not identity or identity[1]['expires'] <= now: raise Unauthorized('Войдите в приложение')
    user, session, workspace = identity
    if not user or not user['active']: raise Unauthorized('Учётная запись отключена')
    if not workspace or workspace['expires'] and workspace['expires'] <= now: raise Unauthorized('Срок демонстрации завершён. Начните новую.')
    if services.guest_mode and (not user['is_guest'] or workspace['kind'] != 'demo'): raise Unauthorized('Откройте личную демонстрацию')
    return Principal(RequestContext(user['workspace_id'],user['id'],user['role'],user['is_guest'],correlation_id), user, session, workspace)

def new_demo(uow, services, role, now):
    workspace, user = uow.demo.seed_workspace(AUTH, role, now)
    context = RequestContext(workspace['id'], user['id'], user['role'], True)
    raw = services.tokens.new()
    session = uow.auth.create_session(context, {'token_hash':services.tokens.digest(raw),'user_id':user['id'],'csrf':services.tokens.new(),'expires':workspace['expires']})
    return SessionResult(session_view(user, session, True), raw, max(1,int((session['expires']-now).total_seconds())))

class GetSession:
    def __init__(self, services): self.services = services
    def execute(self, raw_token, correlation_id=''):
        with self.services.uow(AUTH) as uow:
            return principal(uow.auth.session_identity(AUTH, self.services.tokens.digest(raw_token)), self.services, correlation_id)

class StartGuest:
    def __init__(self, services): self.services = services
    def execute(self, role, raw_token, client_ip, correlation_id=''):
        if not self.services.guest_mode: raise NotFound('Not Found')
        with self.services.uow(AUTH) as uow:
            identity = uow.auth.session_identity(AUTH, self.services.tokens.digest(raw_token))
            try:
                current = principal(identity, self.services, correlation_id)
                if current.user['is_guest'] and current.workspace['kind']=='demo': return SessionResult(session_view(current.user, current.session))
            except Unauthorized:
                pass
        started = time.monotonic()
        self.services.consume('guest', [bucket('guest','guest:'+client_ip,10,900)], correlation_id)
        with self.services.uow(AUTH) as uow:
            now = self.services.clock.now()
            uow.demo.reserve_capacity(AUTH, now)
            result = new_demo(uow, self.services, role, now)
            uow.commit()
        logging.getLogger('schedule.events').info('mutation_committed use_case=guest policy=guest outcome=committed duration_ms=%d correlation_id=%s',int((time.monotonic()-started)*1000),correlation_id)
        return result

class Login:
    def __init__(self, services): self.services = services
    def execute(self, username, password, old_token, client_ip, correlation_id=''):
        if self.services.guest_mode: raise NotFound('Not Found')
        started = time.monotonic()
        self.services.consume('login', [bucket('ip','ip:'+client_ip,60,900),bucket('account','account:'+username.lower(),10,900)], correlation_id)
        with self.services.uow(AUTH) as uow:
            user = uow.auth.find_user(AUTH, username)
            valid = self.services.passwords.verify(password, user['password_hash'] if user else self.services.passwords.dummy_hash)
            if not user or not user['active'] or not valid: raise Unauthorized('Неверный логин или пароль')
            context = RequestContext(user['workspace_id'],user['id'],user['role'],user['is_guest'],correlation_id)
            user = uow.auth.lock_user(context)
            if not user['active']: raise Unauthorized('Учётная запись отключена')
            now = self.services.clock.now()
            uow.auth.cap_sessions(context, self.services.tokens.digest(old_token), now)
            raw, csrf = self.services.tokens.new(), self.services.tokens.new()
            uow.auth.create_session(context, {'token_hash':self.services.tokens.digest(raw),'user_id':user['id'],'csrf':csrf,'expires':now+timedelta(hours=8)})
            uow.commit()
        logging.getLogger('schedule.events').info('mutation_committed use_case=login policy=login outcome=committed duration_ms=%d correlation_id=%s',int((time.monotonic()-started)*1000),correlation_id)
        return SessionResult({'user':user_view(user),'csrf':csrf}, raw, 28800)

class UpdateProfile:
    def __init__(self, services): self.services = services
    def execute(self, current, data):
        context = current.context
        if not context.is_guest: raise Forbidden('Выбор роли доступен только в личной демонстрации')
        with self.services.transaction(context, 'profile_update') as uow:
            values = {'role':data.role, 'group_id':None, 'teacher_id':None}
            for role, kind, field in [('student','groups','group_id'),('teacher','teachers','teacher_id')]:
                if data.role != role: continue
                obj = uow.catalog.get_directory(context, kind, getattr(data,field))
                if obj is None or not obj['active']: raise Validation('Сначала добавьте активную группу или преподавателя в справочник')
                values[field] = obj['id']
            if data.name is not None: values['name'] = data.name
            user = uow.auth.update_profile(context, values)
            result = session_view(user, current.session)
        return result

class ResetGuest:
    def __init__(self, services): self.services = services
    def execute(self, current, client_ip):
        context = current.context
        if not context.is_guest or current.workspace['kind'] != 'demo': raise Forbidden()
        with self.services.transaction(context, 'guest_reset', [bucket('guest','guest:'+client_ip,10,900)]) as uow:
            now = self.services.clock.now()
            actor = uow.auth.lock_user(context)
            uow.demo.reserve_capacity(AUTH, now, context.workspace_id)
            uow.demo.delete_workspace(context)
            result = new_demo(uow, self.services, actor['role'], now)
        return result

class Logout:
    def __init__(self, services): self.services = services
    def execute(self, current):
        with self.services.transaction(current.context, 'logout') as uow:
            uow.auth.delete_session(current.context, current.session['token_hash'])
        return {'ok':True}
