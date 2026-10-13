"""Explicit, rate-limited expired-demo maintenance use case."""
from .bootstrap import services_for
from .db import SessionLocal
from .application.maintenance import CleanupExpiredDemos

if __name__ == '__main__':
    with SessionLocal() as db:
        count = CleanupExpiredDemos(services_for(db)).execute()
    print(f'Expired demo workspaces removed: {count}')
