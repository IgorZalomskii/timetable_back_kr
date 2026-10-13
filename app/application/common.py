import hashlib
import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, replace
from .ports import UowFactory, MutationLimiter, Clock, TokenService, PasswordHasher, LimitBucket
from app.domain.errors import Unauthorized, Forbidden, DependencyUnavailable, RateLimited

def user_view(user):
    return {key:user[key] for key in ('id','name','role','active','group_id','teacher_id','workspace_id','is_guest')}

def session_view(user, session, created=False):
    return {'user':user_view(user), 'csrf':session['csrf'], 'expires_at':session['expires'], 'created':created}

def editor(context):
    if not context.can_edit:
        raise Forbidden('Изменять расписание может только диспетчер или администратор')

def admin(context):
    if context.role != 'admin': raise Forbidden('Нужны права администратора')

def bucket(name, subject, limit, window):
    return LimitBucket(name, hashlib.sha256(subject.encode()).hexdigest(), limit, window)

@dataclass
class Services:
    uow: UowFactory
    limiter: MutationLimiter
    clock: Clock
    tokens: TokenService
    passwords: PasswordHasher
    guest_mode: bool

    def consume(self, policy, buckets, correlation_id=''):
        try:
            decision = self.limiter.consume(policy, buckets)
        except DependencyUnavailable:
            logging.getLogger('schedule.events').warning('redis_unavailable use_case=%s policy=%s outcome=unavailable correlation_id=%s',policy,policy,correlation_id)
            raise
        if not decision.allowed:
            logging.getLogger('schedule.events').warning('rate_limit_denied policy=%s outcome=denied correlation_id=%s', policy, correlation_id)
            raise RateLimited(policy, decision.retry_after)

    def write_gate(self, context, policy, extra=()):
        self.consume(policy, [bucket('workspace', 'write:'+str(context.workspace_id), 120, 60), *extra], context.correlation_id)

    @contextmanager
    def transaction(self, context, policy, extra=(), guard=None):
        # Limiter must finish before opening a mutating PostgreSQL UoW.
        self.write_gate(context, policy, extra)
        started = time.monotonic()
        with self.uow(context) as uow:
            uow.lock_workspace(context.workspace_id)
            # A role/disable may have committed while this writer waited for the lock.
            actor = uow.auth.lock_user(context)
            if not actor or not actor['active']:
                raise Unauthorized('Учётная запись отключена')
            if guard is not None:
                guard(replace(context, role=actor['role']))
            yield uow
            uow.commit()
        logging.getLogger('schedule.events').info('mutation_committed use_case=%s outcome=committed duration_ms=%d correlation_id=%s', policy, int((time.monotonic()-started)*1000), context.correlation_id)
