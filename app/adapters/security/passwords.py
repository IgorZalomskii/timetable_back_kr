import hashlib
import hmac
import secrets

def password_hash(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return f'{salt}:{digest}'

def verify_password(password: str, stored: str) -> bool:
    if ':' not in stored: return False
    salt, expected = stored.split(':',1)
    actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return hmac.compare_digest(actual, expected)

class ScryptPasswordHasher:
    hash = staticmethod(password_hash)
    verify = staticmethod(verify_password)
    def __init__(self): self.dummy_hash = password_hash('non-user-timing-placeholder')
