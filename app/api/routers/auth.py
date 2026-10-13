from fastapi import APIRouter, Depends, Request, Response
from app.schemas import GuestIn, LoginIn, ProfileIn
from app.application.dto import ProfileCommand
from app.application.auth import StartGuest, Login, Logout, UpdateProfile, ResetGuest
from app.api.dependencies import get_services, current_user, guest_request, client_ip
from app.api.presenters import set_session_cookie, clear_session_cookie, session_view

router = APIRouter(prefix='/api/v1/auth')

@router.post('/guest')
def guest(data: GuestIn, request: Request, response: Response, services=Depends(get_services)):
    guest_request(request, services)
    result = StartGuest(services).execute(data.role,request.cookies.get('schedule_session',''),client_ip(request),request.state.correlation_id)
    return set_session_cookie(response,result)

@router.put('/profile')
def profile(data: ProfileIn, current=Depends(current_user), services=Depends(get_services)):
    return UpdateProfile(services).execute(current,ProfileCommand(**data.model_dump()))

@router.post('/guest/reset')
def reset_guest(request: Request,response: Response,current=Depends(current_user),services=Depends(get_services)):
    guest_request(request,services)
    return set_session_cookie(response,ResetGuest(services).execute(current,client_ip(request)))

@router.post('/login')
def login(data: LoginIn,request: Request,response: Response,services=Depends(get_services)):
    result = Login(services).execute(data.username,data.password,request.cookies.get('schedule_session',''),client_ip(request),request.state.correlation_id)
    return set_session_cookie(response,result)

@router.get('/me')
def me(current=Depends(current_user)):
    return session_view(current.user,current.session)

@router.post('/logout')
def logout(response: Response,current=Depends(current_user),services=Depends(get_services)):
    result = Logout(services).execute(current)
    clear_session_cookie(response)
    return result
