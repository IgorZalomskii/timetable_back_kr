import logging
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError, TimeoutError as PoolTimeoutError
from app.domain.errors import Conflict, DependencyUnavailable
from app.domain.values import RequestContext
from . import tenancy
from .auth_repository import AuthRepository
from .demo_repository import DemoRepository
from .catalog_repository import CatalogRepository
from .schedule_repository import ScheduleRepository

class SqlUnitOfWork:
    def __init__(self, db, context):
        self.db, self.context = db, context
        self.committed = False
        self.auth = AuthRepository(db)
        self.demo = DemoRepository(db)
        self.catalog = CatalogRepository(db)
        self.schedules = ScheduleRepository(db)

    def __enter__(self):
        self.db.info.clear()
        if isinstance(self.context,RequestContext):
            self.db.info.update(workspace_id=self.context.workspace_id,guest=self.context.is_guest)
        return self

    def __exit__(self, kind, exc, traceback):
        try:
            if not self.committed: self.rollback()
        finally:
            self.db.expunge_all(); self.db.info.clear()
        if isinstance(exc,IntegrityError):
            raise Conflict('Данные конфликтуют с существующей записью. Обновите список и проверьте занятость и уникальность названия.') from exc
        if isinstance(exc,(OperationalError,PoolTimeoutError)):
            sqlstate = getattr(getattr(exc,'orig',None),'sqlstate',None)
            event = 'workspace_lock_timeout' if sqlstate == '55P03' else 'db_unavailable'
            logging.getLogger('schedule.events').warning('%s outcome=unavailable error=%s correlation_id=%s',event,type(exc).__name__,getattr(self.context,'correlation_id',''))
            raise DependencyUnavailable('postgresql') from exc

    def commit(self):
        self.db.commit(); self.committed = True

    def rollback(self): self.db.rollback()

    def health(self): self.db.execute(text('SELECT 1'))

    def lock_workspace(self, workspace_id, timeout_ms=2000):
        if not isinstance(self.context,RequestContext) or self.context.workspace_id != workspace_id:
            raise ValueError('Workspace lock must match the explicit unit-of-work context')
        self.db.execute(text("SELECT set_config('lock_timeout', :timeout, true)"),{'timeout':f'{int(timeout_ms)}ms'})
        self.db.execute(text('SELECT pg_advisory_xact_lock(7322026, :workspace)'),{'workspace':workspace_id})
