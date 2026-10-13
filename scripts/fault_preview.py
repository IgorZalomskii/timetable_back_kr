"""LOCAL ONLY: browser recovery QA; never include this wrapper in production.

Run on loopback: uvicorn scripts.fault_preview:app --host 127.0.0.1 --port 8190
Control .local/qa-fault.json: {"path":"/api/v1/auth/profile","mode":"lost-response"}.
Modes: hang (no mutation), lost-response (commit but stall body), error (503).
"""
import asyncio
import json
from pathlib import Path
from scripts.preview import app as application
from app.db import APP_ENV
from starlette.responses import JSONResponse

if APP_ENV != 'development':
    raise RuntimeError('Fault preview requires APP_ENV=development')

async def app(scope, receive, send):
    if scope['type'] != 'http':
        return await application(scope, receive, send)
    control = Path(__file__).resolve().parents[1] / '.local' / 'qa-fault.json'
    config = json.loads(control.read_text()) if control.exists() else {}
    if not config.get('path') or not scope['path'].endswith(config['path']):
        return await application(scope, receive, send)
    mode = config.get('mode')
    if mode == 'hang':
        await asyncio.sleep(20)
        return await JSONResponse({'detail':'QA simulated timeout'},status_code=503)(scope,receive,send)
    if mode == 'error':
        return await JSONResponse({'detail':'QA temporary failure'},status_code=503)(scope,receive,send)
    if mode == 'lost-response':
        messages = []
        async def capture(message):
            messages.append(message)
        await application(scope, receive, capture)
        await asyncio.sleep(20)
        for message in messages:
            await send(message)
        return
    await application(scope, receive, send)
