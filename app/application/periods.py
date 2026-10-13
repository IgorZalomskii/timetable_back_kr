from dataclasses import asdict
from .common import editor

class ListPeriods:
    def __init__(self, services): self.services = services
    def execute(self, context):
        with self.services.uow(context) as uow: return uow.catalog.list_periods(context)

class CreatePeriod:
    def __init__(self, services): self.services = services
    def execute(self, context, data):
        editor(context)
        with self.services.transaction(context, 'period_create', guard=editor) as uow: result = uow.catalog.create_period(context, asdict(data))
        return result
