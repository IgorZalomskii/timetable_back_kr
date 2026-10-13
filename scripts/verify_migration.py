"""Non-destructive fresh-schema verification in a uniquely named disposable database."""
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.db import engine, ROOT
from sqlalchemy import create_engine, inspect, text

if engine.url.host != '127.0.0.1' or engine.url.port != int(os.environ.get('SCHEDULE_PG_PORT','55439')):
    raise SystemExit('This check runs only against the private local cluster')
name='schedule_verify_'+uuid4().hex[:10]
with engine.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
    connection.execute(text(f'CREATE DATABASE "{name}"'))
url=engine.url.set(database=name)
environment=dict(os.environ,DATABASE_URL=url.render_as_string(hide_password=False),APP_ENV='development')
for command in (['alembic','upgrade','head'],['alembic','upgrade','head'],['app.seed']):
    subprocess.run([sys.executable,'-m',*command],cwd=ROOT,env=environment,check=True)
verification=create_engine(url)
with verification.connect() as connection:
    assert connection.scalar(text('SELECT version_num FROM alembic_version'))=='0002'
    assert connection.scalar(text('SELECT count(*) FROM users'))==4
    assert connection.scalar(text('SELECT count(*) FROM lessons'))==30
    assert len(inspect(connection).get_table_names())==14
    assert connection.scalar(text('SELECT count(*) FROM users WHERE workspace_id=1'))==4
verification.dispose()
print(f'FRESH MIGRATION AND SEED VERIFIED; isolated database retained: {name}')
