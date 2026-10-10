"""Remove only expired demo workspaces; legacy data is never selected."""
from .db import SessionLocal
from .demo import cleanup

if __name__=='__main__':
    with SessionLocal.begin() as db:
        count=cleanup(db)
    print(f'Expired demo workspaces removed: {count}')
