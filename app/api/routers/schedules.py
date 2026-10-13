from fastapi import APIRouter, Depends
from app.schemas import ScheduleIn
from app.application.dto import ScheduleCommand
from app.application.schedules import ListSchedules, CreateSchedule, PublishSchedule
from app.api.dependencies import get_services, current_user, editor

router = APIRouter(prefix='/api/v1/schedules')
@router.get('')
def schedules(current=Depends(current_user),services=Depends(get_services)):
    return ListSchedules(services).execute(current.context)

@router.post('',status_code=201)
def add_schedule(data: ScheduleIn,current=Depends(editor),services=Depends(get_services)):
    return CreateSchedule(services).execute(current.context,ScheduleCommand(**data.model_dump()))

@router.post('/{ident}/publish')
def publish(ident: int,current=Depends(editor),services=Depends(get_services)):
    return PublishSchedule(services).execute(current.context,ident)
