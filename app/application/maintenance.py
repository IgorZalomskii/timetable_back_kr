from app.domain.values import SystemContext
from .common import bucket

class HealthQuery:
    def __init__(self, services): self.services = services
    def execute(self):
        with self.services.uow(SystemContext('health')) as uow: uow.health()
        return {'status':'ok'}

class CleanupExpiredDemos:
    def __init__(self, services): self.services = services
    def execute(self):
        self.services.consume('cleanup', [bucket('system','expired-demo-cleanup',120,60)])
        with self.services.uow(SystemContext('cleanup')) as uow:
            count = uow.demo.cleanup_expired(SystemContext('cleanup'), self.services.clock.now())
            uow.commit()
        return count
