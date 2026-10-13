"""Create a private loopback-only dev PostgreSQL cluster, never touch system clusters."""
import os
import secrets
import subprocess
import sys
from pathlib import Path
import psycopg

ROOT=Path(__file__).resolve().parents[1]
local=ROOT/'.local'; local.mkdir(exist_ok=True)
if os.name != 'nt':
    os.chmod(local, 0o700)
    os.umask(0o077)
binpath=Path(os.environ.get('PG_BIN',r'C:\Program Files\PostgreSQL\15\bin'))
port=int(os.environ.get('SCHEDULE_PG_PORT','55439'))
data=local/'postgres'
flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0

def run(args):
    subprocess.run([str(x) for x in args],check=True,creationflags=flags)

secret=local/'db-password'
if not secret.exists():
    secret.write_text(secrets.token_hex(24),encoding='ascii')
password=secret.read_text(encoding='ascii').strip()
if os.name != 'nt':
    os.chmod(secret, 0o600)
if not (data/'PG_VERSION').exists():
    run([binpath/'initdb','-D',data,'-U','schedule','--pwfile',secret,'-A','scram-sha-256','--encoding=UTF8','--locale=C'])
if subprocess.run([str(binpath/'pg_ctl'),'-D',str(data),'status'],capture_output=True,creationflags=flags).returncode:
    run([binpath/'pg_ctl','-D',data,'-l',local/'postgres.log','-o',f'-p {port} -h 127.0.0.1','-w','start'])
with psycopg.connect(host='127.0.0.1',port=port,user='schedule',password=password,dbname='postgres',autocommit=True) as conn:
    for name in ('schedule','schedule_test'):
        if not conn.execute('SELECT 1 FROM pg_database WHERE datname=%s',(name,)).fetchone():
            conn.execute(psycopg.sql.SQL('CREATE DATABASE {}').format(psycopg.sql.Identifier(name)))
env=ROOT/'.env'
if not env.exists():
    env.write_text(f'DATABASE_URL=postgresql+psycopg://schedule:{password}@127.0.0.1:{port}/schedule\nAPP_ENV=development\n',encoding='utf-8')
if os.name != 'nt':
    os.chmod(env, 0o600)
print(f'Private PostgreSQL ready at 127.0.0.1:{port}; databases schedule and schedule_test')
