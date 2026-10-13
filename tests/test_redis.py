import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from redis.exceptions import TimeoutError, ResponseError
from app.adapters.redis.limiter import RedisMutationLimiter
from app.application.common import bucket
from app.domain.errors import DependencyUnavailable

@pytest.fixture
def limiter():
    url=os.environ.get('REDIS_URL')
    if not url: pytest.skip('REDIS_URL is required for Redis integration tests')
    limiter=RedisMutationLimiter(url,'test-'+uuid.uuid4().hex)
    limiter.startup()
    yield limiter
    for key in limiter.client.scan_iter(match=limiter.namespace+':*'): limiter.client.delete(key)
    limiter.client.close()

def test_atomic_multi_bucket_concurrency_and_no_partial_reservation(limiter):
    ip=bucket('ip','private-ip',100,60); account=bucket('account','private-account',10,60)
    with ThreadPoolExecutor(max_workers=20) as executor:
        decisions=list(executor.map(lambda _:limiter.consume('login',[ip,account]),range(40)))
    assert sum(x.allowed for x in decisions)==10
    assert int(limiter.client.get(limiter.key(ip)))==10
    assert int(limiter.client.get(limiter.key(account)))==10
    assert all(1 <= x.retry_after <= 60 for x in decisions if not x.allowed)
    assert 'private' not in limiter.key(account)

def test_ttl_expiry_noscript_and_denial_do_not_extend_window(limiter):
    entry=bucket('workspace','private-workspace',1,1)
    assert limiter.consume('profile',[entry]).allowed
    before=limiter.client.pttl(limiter.key(entry))
    assert not limiter.consume('logout',[entry]).allowed
    assert limiter.client.pttl(limiter.key(entry)) <= before
    time.sleep(1.05)
    assert limiter.consume('profile',[entry]).allowed
    # NOSCRIPT via an incorrect SHA reloads exactly once and cannot partially apply.
    limiter.sha='0'*40
    with pytest.raises(DependencyUnavailable): limiter.consume('profile',[entry])

def test_real_script_flush_reload(limiter):
    # SCRIPT FLUSH is global: use isolated recovery Redis only.
    limiter.client.script_flush()
    assert limiter.consume('new',[bucket('workspace','other',1,60)]).allowed

@pytest.mark.parametrize('error',[TimeoutError('test'),ResponseError('test script failure')])
def test_errors_fail_closed_without_retry(limiter,monkeypatch,error):
    calls=[]
    def fail(*args): calls.append(args); raise error
    monkeypatch.setattr(limiter.client,'evalsha',fail)
    with pytest.raises(DependencyUnavailable) as exc: limiter.consume('profile',[bucket('workspace','other',1,60)])
    assert exc.value.dependency=='redis' and len(calls)==1

def test_missing_ttl_is_repaired_on_allowed_bucket(limiter):
    entry=bucket('workspace','other',3,60)
    limiter.client.set(limiter.key(entry),1)
    assert limiter.consume('profile',[entry]).allowed
    assert 0 < limiter.client.pttl(limiter.key(entry)) <= 60000
