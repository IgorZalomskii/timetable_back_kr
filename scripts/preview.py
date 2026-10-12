"""Loopback-only preview of the exact /mireabackr production build."""
from app.main import app as application

async def app(scope, receive, send):
    if scope['type']=='http' and scope['path'].startswith('/mireabackr/'):
        scope=dict(scope,path=scope['path'][len('/mireabackr'):])
    await application(scope,receive,send)
