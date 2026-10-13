import hashlib
import logging
import math
from pathlib import Path
from redis import Redis
from redis.exceptions import RedisError, NoScriptError
from redis.retry import Retry
from redis.backoff import NoBackoff
from app.application.ports import LimitDecision
from app.domain.errors import DependencyUnavailable

class RedisMutationLimiter:
    def __init__(self, url, environment, connect_timeout_ms=250, read_timeout_ms=250):
        if not 0 < connect_timeout_ms <= 250 or not 0 < read_timeout_ms <= 250:
            raise ValueError('Redis timeouts must be between 1 and 250 milliseconds')
        self.client = Redis.from_url(url, socket_connect_timeout=connect_timeout_ms/1000,socket_timeout=read_timeout_ms/1000,retry=Retry(NoBackoff(),0),retry_on_timeout=False,decode_responses=True)
        self.namespace = f'schedule:{environment}:rl:v1'
        self.script = (Path(__file__).parent/'scripts'/'consume_limits.lua').read_text(encoding='utf-8')
        self.sha = hashlib.sha1(self.script.encode()).hexdigest()

    def key(self, bucket):
        # Bucket name, not route, intentionally shares workspace and guest quotas.
        return f'{self.namespace}:{bucket.name}:{bucket.subject}'

    def startup(self):
        self.client.ping()
        self.client.script_load(self.script)

    def consume(self, policy, buckets):
        keys = [self.key(bucket) for bucket in buckets]
        args = [value for bucket in buckets for value in (bucket.limit,bucket.window_seconds*1000)]
        try:
            try: result = self.client.evalsha(self.sha,len(keys),*keys,*args)
            except NoScriptError:
                self.client.script_load(self.script)
                result = self.client.evalsha(self.sha,len(keys),*keys,*args)
            return LimitDecision(bool(result[0]), max(1,math.ceil(int(result[1])/1000)) if not result[0] else 0)
        except (RedisError,ValueError,TypeError,IndexError) as exc:
            logging.getLogger('schedule.events').warning('redis_unavailable policy=%s outcome=unavailable error=%s',policy,type(exc).__name__)
            raise DependencyUnavailable('redis') from exc
