import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

ROOT = Path(__file__).resolve().parents[1]
if (ROOT / '.env').exists():
    for line in (ROOT / '.env').read_text(encoding='utf-8').splitlines():
        if '=' in line and not line.startswith('#'):
            key, value = line.split('=', 1)
            os.environ.setdefault(key.strip(), value.strip())

APP_ENV = os.environ.get('APP_ENV', 'production')
if APP_ENV not in ('development', 'test', 'production'):
    raise RuntimeError('APP_ENV must be development, test or production')
DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    raise RuntimeError('DATABASE_URL is required; run scripts/devdb.py for local development')
if APP_ENV == 'production' and not os.environ.get('PUBLIC_ORIGIN', '').startswith('https://'):
    raise RuntimeError('Production requires PUBLIC_ORIGIN=https://your-domain')
DB_CONNECT_ARGS = {'connect_timeout': 5, 'options': '-c statement_timeout=10000 -c lock_timeout=2000 -c idle_in_transaction_session_timeout=15000'}
engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_timeout=5, connect_args=DB_CONNECT_ARGS)
SessionLocal = sessionmaker(engine, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

def get_db():
    with SessionLocal() as db:
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
