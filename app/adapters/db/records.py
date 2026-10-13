from sqlalchemy import select
from app.domain.errors import NotFound

def record(obj, private=False):
    if obj is None: return None
    return {column.name:getattr(obj,column.name) for column in obj.__table__.columns if private or column.name != 'workspace_id'}

def owned(db, model, context, ident):
    obj = db.scalar(select(model).where(model.workspace_id==context.workspace_id, model.id==ident))
    if obj is None: raise NotFound()
    return obj
