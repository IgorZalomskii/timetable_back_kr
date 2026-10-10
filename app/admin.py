"""Interactive first administrator creation, password never passed in command arguments."""
from getpass import getpass
from sqlalchemy import select
from .db import SessionLocal
from .models import User
from .schemas import UserIn
from .security import password_hash

if __name__=='__main__':
    data=UserIn(username=input('Login: ').strip(),name=input('Name: ').strip(),password=getpass('Password (10+ characters): '),role='admin')
    with SessionLocal.begin() as db:
        db.info['workspace_id']=1
        if db.scalar(select(User.id).where(User.username==data.username)):
            raise SystemExit('User already exists; no changes')
        db.add(User(username=data.username,name=data.name,role='admin',password_hash=password_hash(data.password)))
    print('Administrator created')
