import hmac
from fastapi import Depends, Request
from app.application.auth import GetSession
from app.application.common import editor as require_editor, admin as require_admin
from app.domain.errors import Forbidden, NotFound
from . import config

def get_services():
    raise RuntimeError('Application services must be wired by bootstrap.create_app')

def current_user(request: Request, services=Depends(get_services)):
    current = GetSession(services).execute(request.cookies.get('schedule_session',''),request.state.correlation_id)
    if request.method not in ('GET','HEAD','OPTIONS'):
        if not hmac.compare_digest(request.headers.get('x-csrf-token',''),current.session['csrf']):
            raise Forbidden('Обновите страницу и повторите действие')
    return current

def editor(current=Depends(current_user)):
    require_editor(current.context)
    return current

def admin(current=Depends(current_user)):
    require_admin(current.context)
    return current

def guest_request(request, services):
    if not services.guest_mode: raise NotFound('Not Found')
    expected = config.PUBLIC_ORIGIN or str(request.base_url).rstrip('/')
    if request.headers.get('origin') != expected or request.headers.get('x-requested-with') != 'schedule-app' or not request.headers.get('content-type','').startswith('application/json'):
        raise Forbidden('Откройте приложение на его сайте и повторите действие')

def client_ip(request):
    # The trusted proxy/Uvicorn boundary resolves forwarded addresses, never this layer.
    return request.client.host if request.client else 'unknown'
