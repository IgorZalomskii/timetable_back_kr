from fastapi import APIRouter, Depends
from app.schemas import UserIn
from app.application.dto import UserCommand
from app.application.users import ListUsers, CreateUser, ToggleUser
from app.api.dependencies import get_services, admin

router = APIRouter(prefix='/api/v1/users')
@router.get('')
def users(current=Depends(admin),services=Depends(get_services)):
    return ListUsers(services).execute(current.context)

@router.post('',status_code=201)
def add_user(data: UserIn,current=Depends(admin),services=Depends(get_services)):
    return CreateUser(services).execute(current.context,UserCommand(**data.model_dump()))

@router.post('/{ident}/toggle')
def toggle_user(ident: int,current=Depends(admin),services=Depends(get_services)):
    return ToggleUser(services).execute(current.context,ident)
