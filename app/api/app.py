import logging
import time
import uuid
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from app.limits import BodyLimit
from . import config
from .errors import install_errors
from .routers import health, auth, directories, users, periods, schedules, lessons, series

def create_http_app(root, lifespan):
    app = FastAPI(title='Расписание — сервер учебного расписания',version='2.0.0',docs_url='/docs' if not config.PRODUCTION else None,redoc_url=None,openapi_url='/openapi.json' if not config.PRODUCTION else None,lifespan=lifespan)
    app.add_middleware(BodyLimit)
    install_errors(app)

    @app.middleware('http')
    async def headers(request: Request,call_next):
        started = time.monotonic()
        request.state.correlation_id = uuid.uuid4().hex
        if request.method not in ('GET','HEAD','OPTIONS'):
            origin = request.headers.get('origin')
            expected = config.PUBLIC_ORIGIN or str(request.base_url).rstrip('/')
            if origin and origin != expected: return JSONResponse({'detail':'Недопустимый источник запроса'},status_code=403)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        if config.PRODUCTION:
            response.headers['X-Frame-Options'] = 'DENY'
            response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; base-uri 'self'"
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['X-Request-ID'] = request.state.correlation_id
        if request.url.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        route = request.scope.get('route')
        logging.getLogger('schedule.events').info('request_finished route=%s status=%s duration_ms=%d correlation_id=%s',getattr(route,'path','unmatched'),response.status_code,int((time.monotonic()-started)*1000),request.state.correlation_id)
        return response

    for module in (health,auth,directories,users,periods,schedules,lessons,series): app.include_router(module.router)
    dist = root/'frontend'/'dist'
    if dist.exists():
        app.mount('/assets',StaticFiles(directory=dist/'assets'),name='assets')
        @app.get('/')
        def index(): return FileResponse(dist/'index.html')
    return app
