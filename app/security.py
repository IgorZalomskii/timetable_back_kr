import hashlib
import hmac
import os
import secrets
from datetime import datetime, timezone, timedelta
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select, func, delete
from .db import get_db
from .models import Session, User, Workspace, LoginAttempt
from . import workspaces  # install request-scoped ORM ownership guards

def guest_mode():
    return os.environ.get('GUEST_MODE', '1') == '1'

def password_hash(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return f'{salt}:{digest}'

def verify_password(password: str, stored: str) -> bool:
    salt, expected = stored.split(':')
    actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return hmac.compare_digest(actual, expected)

def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

def current_user(request: Request, db=Depends(get_db)):
    session = db.get(Session, token_hash(request.cookies.get('schedule_session', '')))
    if not session or session.expires <= datetime.now(timezone.utc):
        raise HTTPException(401, 'Войдите в приложение')
    user = db.get(User, session.user_id)
    if not user or not user.active:
        raise HTTPException(401, 'Учётная запись отключена')
    workspace = db.get(Workspace, user.workspace_id)
    if not workspace or (workspace.expires and workspace.expires <= datetime.now(timezone.utc)):
        raise HTTPException(401, 'Срок демонстрации завершён. Начните новую.')
    if guest_mode() and (not user.is_guest or workspace.kind != 'demo'):
        raise HTTPException(401, 'Откройте личную демонстрацию')
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        if not hmac.compare_digest(request.headers.get('x-csrf-token', ''), session.csrf):
            raise HTTPException(403, 'Обновите страницу и повторите действие')
        if user.is_guest:
            from .services import lock_writes
            db.info['workspace_id'] = user.workspace_id
            lock_writes(db)
            db.refresh(user)
            key = token_hash('write:'+str(user.workspace_id))
            cutoff = datetime.now(timezone.utc)-timedelta(minutes=1)
            db.execute(delete(LoginAttempt).where(LoginAttempt.key==key, LoginAttempt.created<cutoff))
            if db.scalar(select(func.count()).select_from(LoginAttempt).where(LoginAttempt.key==key)) >= 120:
                raise HTTPException(429, 'Слишком много действий. Подождите минуту.')
            db.add(LoginAttempt(key=key))
    request.state.session = session
    request.state.workspace = workspace
    db.info['workspace_id'] = user.workspace_id
    db.info['guest'] = user.is_guest
    return user

def editor(user=Depends(current_user)):
    if user.role not in ('admin', 'dispatcher'):
        raise HTTPException(403, 'Изменять расписание может только диспетчер или администратор')
    return user

def admin(user=Depends(current_user)):
    if user.role != 'admin':
        raise HTTPException(403, 'Нужны права администратора')
    return user

def user_view(user):
    return {key: getattr(user, key) for key in ('id', 'name', 'role', 'active', 'group_id', 'teacher_id', 'workspace_id', 'is_guest')}
