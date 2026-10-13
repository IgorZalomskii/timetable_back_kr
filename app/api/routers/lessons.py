from datetime import date
from fastapi import APIRouter, Depends, Query
from app.schemas import LessonIn, ChangeIn, CancelIn
from app.application.dto import LessonCommand, MoveCommand, CancelCommand
from app.application.lessons import ListLessons, CreateLesson, MoveLesson, CancelLesson, GetHistory
from app.api.dependencies import get_services, current_user, editor

router = APIRouter(prefix='/api/v1/lessons')
@router.get('')
def lessons(start: date,end: date,group_id: int | None=None,teacher_id: int | None=None,room_id: int | None=None,schedule_id: int | None=None,offset: int=Query(0,ge=0),limit: int=Query(200,ge=1,le=500),current=Depends(current_user),services=Depends(get_services)):
    return ListLessons(services).execute(current.context,start,end,{'group_id':group_id,'teacher_id':teacher_id,'room_id':room_id,'schedule_id':schedule_id},offset,limit)

@router.post('',status_code=201)
def add_lesson(data: LessonIn,current=Depends(editor),services=Depends(get_services)):
    return CreateLesson(services).execute(current.context,LessonCommand(**data.model_dump()))

@router.put('/{ident}')
def change_lesson(ident: int,data: ChangeIn,current=Depends(editor),services=Depends(get_services)):
    return MoveLesson(services).execute(current.context,ident,MoveCommand(**data.model_dump()))

@router.post('/{ident}/cancel')
def cancel_lesson(ident: int,data: CancelIn,current=Depends(editor),services=Depends(get_services)):
    return CancelLesson(services).execute(current.context,ident,CancelCommand(**data.model_dump()))

@router.get('/{ident}/history')
def lesson_history(ident: int,current=Depends(current_user),services=Depends(get_services)):
    return GetHistory(services).execute(current.context,ident)
