from fastapi.responses import JSONResponse
from app.domain.errors import (ApplicationError, NotFound, Forbidden, Unauthorized,
    Conflict, Validation, BulkWriteRejected, CapacityExceeded, RateLimited, DependencyUnavailable)

TEMPORARILY_UNAVAILABLE = 'Сервер занят или база временно недоступна. Подождите несколько секунд и проверьте состояние данных.'
RATE_LIMIT_MESSAGES = {
    'login':'Слишком много попыток. Повторите через 15 минут.',
    'guest':'Слишком много новых демонстраций. Попробуйте через 15 минут.',
}

def present_error(exc):
    if isinstance(exc, DependencyUnavailable):
        return JSONResponse({'detail':TEMPORARILY_UNAVAILABLE},status_code=503,headers={'Retry-After':'3'})
    if isinstance(exc, RateLimited):
        detail = RATE_LIMIT_MESSAGES.get(exc.policy,'Слишком много действий. Подождите минуту.')
        return JSONResponse({'detail':detail},status_code=429,headers={'Retry-After':str(exc.retry_after_seconds)})
    statuses = {NotFound:404, Forbidden:403, Unauthorized:401, Conflict:409,
                Validation:422, BulkWriteRejected:400, CapacityExceeded:503}
    for error_type,status in statuses.items():
        if isinstance(exc,error_type):
            return JSONResponse({'detail':exc.message},status_code=status)
    # Unclassified internal failures must not expose their diagnostic message.
    return JSONResponse({'detail':'Внутренняя ошибка сервера'},status_code=500)

def install_errors(app):
    @app.exception_handler(ApplicationError)
    async def application_error(request, exc):
        return present_error(exc)
