from fastapi import APIRouter, Depends
from app.schemas import PeriodIn
from app.application.dto import PeriodCommand
from app.application.periods import ListPeriods, CreatePeriod
from app.api.dependencies import get_services, current_user, editor

router = APIRouter(prefix='/api/v1/periods')
@router.get('')
def periods(current=Depends(current_user),services=Depends(get_services)):
    return ListPeriods(services).execute(current.context)

@router.post('',status_code=201)
def add_period(data: PeriodIn,current=Depends(editor),services=Depends(get_services)):
    return CreatePeriod(services).execute(current.context,PeriodCommand(**data.model_dump()))
