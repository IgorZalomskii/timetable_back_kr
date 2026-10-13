"""Rebuild only the project's disposable localhost schedule_test tables."""
import sys
import os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from app.db import DATABASE_URL, Base
from app import models

url=make_url(DATABASE_URL).set(database='schedule_test')
if url.host not in ('127.0.0.1','localhost') or url.port != int(os.environ.get('SCHEDULE_PG_PORT','55439')):
    raise SystemExit('This check requires the private local PostgreSQL cluster')
engine=create_engine(url)
if engine.url.database != 'schedule_test':
    raise SystemExit('Refusing to rebuild a non-test database')
Base.metadata.drop_all(engine)
with engine.begin() as db: db.execute(text('CREATE EXTENSION IF NOT EXISTS btree_gist'))
Base.metadata.create_all(engine)
print('Dedicated local test tables rebuilt')
