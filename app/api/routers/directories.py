from fastapi import APIRouter, Depends
from app.schemas import DirectoryIn
from app.application.dto import DirectoryCommand
from app.application.directories import ListDirectory, CreateDirectoryEntry, UpdateDirectoryEntry
from app.api.dependencies import get_services, current_user, admin

router = APIRouter(prefix='/api/v1/directories')
@router.get('/{kind}')
def directory_list(kind: str,current=Depends(current_user),services=Depends(get_services)):
    return ListDirectory(services).execute(current.context,kind)

@router.post('/{kind}',status_code=201)
def directory_create(kind: str,data: DirectoryIn,current=Depends(admin),services=Depends(get_services)):
    return CreateDirectoryEntry(services).execute(current.context,kind,DirectoryCommand(**data.model_dump()))

@router.put('/{kind}/{ident}')
def directory_update(kind: str,ident: int,data: DirectoryIn,current=Depends(admin),services=Depends(get_services)):
    return UpdateDirectoryEntry(services).execute(current.context,kind,ident,DirectoryCommand(**data.model_dump()))
