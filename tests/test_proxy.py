import asyncio
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from app.application.common import bucket

def resolved(peer,forwarded,trusted='10.23.0.2'):
    clients=[]
    async def app(scope,receive,send): clients.append(scope['client'][0])
    middleware=ProxyHeadersMiddleware(app,trusted_hosts=trusted)
    scope={'type':'http','scheme':'http','client':(peer,1234),'headers':[(b'x-forwarded-for',forwarded.encode())]}
    asyncio.run(middleware(scope,None,None))
    return clients[0]

def test_trusted_proxy_preserves_independent_login_ip_buckets():
    first=resolved('10.23.0.2','198.51.100.10')
    second=resolved('10.23.0.2','198.51.100.11')
    assert first=='198.51.100.10' and second=='198.51.100.11'
    assert bucket('ip','ip:'+first,60,900).subject != bucket('ip','ip:'+second,60,900).subject

def test_direct_untrusted_client_cannot_rotate_buckets_with_spoofed_headers():
    first=resolved('198.51.100.12','1.1.1.1')
    second=resolved('198.51.100.12','8.8.8.8')
    assert first==second=='198.51.100.12'
    assert bucket('ip','ip:'+first,60,900)==bucket('ip','ip:'+second,60,900)

def test_forwarded_chain_uses_last_untrusted_address():
    assert resolved('10.23.0.2','6.6.6.6, 198.51.100.10')=='198.51.100.10'
