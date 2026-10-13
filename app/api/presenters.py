from . import config
from app.application.common import session_view

def set_session_cookie(response, result):
    if result.raw_token:
        response.set_cookie('schedule_session',result.raw_token,httponly=True,secure=config.PRODUCTION,samesite='strict',max_age=result.max_age,path=config.COOKIE_PATH)
    return result.body

def clear_session_cookie(response): response.delete_cookie('schedule_session',path=config.COOKIE_PATH)
