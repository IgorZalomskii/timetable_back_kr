from fastapi import APIRouter, Depends
from app.schemas import SeriesIn
from app.application.dto import SeriesCommand
from app.application.series import PreviewSeries, CreateSeries
from app.api.dependencies import get_services, editor

router = APIRouter(prefix='/api/v1/series')
@router.post('/preview')
def preview_series(data: SeriesIn,current=Depends(editor),services=Depends(get_services)):
    return PreviewSeries(services).execute(current.context,SeriesCommand(**data.model_dump()))

@router.post('',status_code=201)
def add_series(data: SeriesIn,current=Depends(editor),services=Depends(get_services)):
    return CreateSeries(services).execute(current.context,SeriesCommand(**data.model_dump()))
