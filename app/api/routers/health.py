from fastapi import APIRouter, Depends
from app.application.maintenance import HealthQuery
from app.api.dependencies import get_services

router = APIRouter(prefix='/api/v1')
@router.get('/health')
def health(services=Depends(get_services)): return HealthQuery(services).execute()
