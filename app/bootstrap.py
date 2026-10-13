"""The composition root is the only consumer that selects concrete adapters."""
import os
import logging
from ipaddress import ip_address
from contextlib import asynccontextmanager
from fastapi import Depends
from sqlalchemy import text
from .adapters.db.base import get_db, SessionLocal, ROOT, APP_ENV
from .adapters.db.uow import SqlUnitOfWork
from .adapters.redis.limiter import RedisMutationLimiter
from .adapters.security.passwords import ScryptPasswordHasher
from .adapters.security.tokens import SecureTokenService, SystemClock
from .application.common import Services
from .api.app import create_http_app
from .api.dependencies import get_services
from .api import config

# Uvicorn reads this same setting. Trust exact proxy addresses only, never '*'/CIDR.
for proxy in os.environ.get('FORWARDED_ALLOW_IPS','127.0.0.1').split(','):
    if proxy.strip(): ip_address(proxy.strip())

limiter = RedisMutationLimiter(os.environ.get('REDIS_URL','redis://127.0.0.1:6379/0'),APP_ENV,int(os.environ.get('REDIS_CONNECT_TIMEOUT_MS','250')),int(os.environ.get('REDIS_READ_TIMEOUT_MS','250')))
passwords = ScryptPasswordHasher()

def services_for(db):
    return Services(lambda context:SqlUnitOfWork(db,context),limiter,SystemClock(),SecureTokenService(),passwords,os.environ.get('GUEST_MODE','1')=='1')

def provide_services(db=Depends(get_db)):
    return services_for(db)

@asynccontextmanager
async def lifespan(app):
    # Migration is a separate deployment job; startup only verifies prerequisites.
    limiter.startup()
    with SessionLocal() as db:
        if db.scalar(text('SELECT version_num FROM alembic_version')) != '0002':
            raise RuntimeError('Schema 0002 is required; run alembic upgrade head before starting')
    yield

def create_app():
    event_logger = logging.getLogger('schedule.events')
    if not event_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
        event_logger.addHandler(handler)
    event_logger.setLevel(logging.INFO)
    event_logger.propagate = False
    config.PRODUCTION = APP_ENV == 'production'
    config.COOKIE_PATH = os.environ.get('APP_BASE_PATH','/').rstrip('/') or '/'
    config.PUBLIC_ORIGIN = os.environ.get('PUBLIC_ORIGIN')
    app = create_http_app(ROOT,lifespan)
    app.dependency_overrides[get_services] = provide_services
    return app
