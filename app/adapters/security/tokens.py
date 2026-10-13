import hashlib
import secrets
from datetime import datetime, timezone

def token_hash(raw): return hashlib.sha256(raw.encode()).hexdigest()

class SecureTokenService:
    digest = staticmethod(token_hash)
    @staticmethod
    def new(): return secrets.token_urlsafe(32)

class SystemClock:
    @staticmethod
    def now(): return datetime.now(timezone.utc)
