"""Fresh migration and preserved legacy fixture, only on private local PostgreSQL."""
import os
import subprocess
import sys
import uuid
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from app.db import DATABASE_URL

root=Path(__file__).resolve().parents[1]
url=make_url(DATABASE_URL)
if url.host not in ('127.0.0.1','localhost') or url.port != int(os.environ.get('SCHEDULE_PG_PORT','55439')):
    raise SystemExit('This check requires the private local PostgreSQL cluster')
name='schedule_verify_guest_'+uuid.uuid4().hex[:10]
admin=create_engine(url.set(database='postgres'),isolation_level='AUTOCOMMIT')
with admin.connect() as db: db.execute(text(f'CREATE DATABASE "{name}"'))
target=create_engine(url.set(database=name))
env=dict(os.environ,DATABASE_URL=url.set(database=name).render_as_string(hide_password=False),APP_ENV='development')
def upgrade(revision):
    subprocess.run([sys.executable,'-m','alembic','upgrade',revision],cwd=root,env=env,check=True)
try:
    upgrade('0001')
    with target.begin() as db:
        db.execute(text("INSERT INTO groups(id,name,size,active) VALUES(1,'Legacy group',20,true)"))
        db.execute(text("INSERT INTO users(id,username,name,password_hash,role,active,group_id) VALUES(1,'legacy','Preserved','unchanged-hash','admin',true,1)"))
    upgrade('head'); upgrade('head')
    with target.begin() as db:
        assert db.execute(text('SELECT name,password_hash,workspace_id,is_guest FROM users WHERE id=1')).one()==('Preserved','unchanged-hash',1,False)
        assert db.execute(text('SELECT workspace_id FROM groups WHERE id=1')).scalar_one()==1
        assert db.execute(text("SELECT count(*) FROM information_schema.columns WHERE table_schema='public' AND column_name='workspace_id' AND column_default IS NOT NULL")).scalar_one()==0
        assert db.execute(text("SELECT count(*) FROM pg_constraint WHERE conname LIKE '%_workspace_fk'")).scalar_one()==24
        db.execute(text("INSERT INTO workspaces(id,kind,expires) VALUES(2,'demo',now()+interval '7 days')"))
        db.execute(text("INSERT INTO groups(id,name,size,active,workspace_id) VALUES(2,'Legacy group',20,true,2)"))
    # Baseline preserved; repeated upgrade and tenant-local duplicate names accepted.
    print('Guest migration verified: legacy preserved, ownership constraints present, upgrade repeatable')
finally:
    target.dispose()
    with admin.connect() as db: db.execute(text(f'DROP DATABASE "{name}"'))
    admin.dispose()
