"""Request-bound data scope. PostgreSQL composite foreign keys also enforce ownership."""
from sqlalchemy import event, select, func
from sqlalchemy.orm import Session as OrmSession, with_loader_criteria
from fastapi import HTTPException
from .models import Scoped, Group, Teacher, Room, Subject, Period, Schedule, Lesson, Series, Audit

LIMITS={Group:100,Teacher:100,Room:100,Subject:100,Period:30,Schedule:50,Lesson:1000,Series:100,Audit:5000}


@event.listens_for(OrmSession, 'do_orm_execute')
def scoped_queries(state):
    workspace_id = state.session.info.get('workspace_id')
    if workspace_id is not None and state.is_select:
        state.statement = state.statement.options(with_loader_criteria(
            Scoped, lambda model: model.workspace_id == workspace_id, include_aliases=True))
    elif workspace_id is not None and (state.is_update or state.is_delete):
        mapper=state.bind_mapper
        if mapper is not None and issubclass(mapper.class_,Scoped):
            # Reject bulk writes: every domain change must pass before_flush guards.
            raise HTTPException(400,'Массовое изменение записей недоступно')


@event.listens_for(OrmSession, 'before_flush')
def scoped_writes(db, context, instances):
    workspace_id = db.info.get('workspace_id')
    if workspace_id is None:
        return
    for obj in db.new | db.dirty | db.deleted:
        if not isinstance(obj, Scoped):
            continue
        if obj in db.new and obj.workspace_id is None:
            obj.workspace_id = workspace_id
        if obj.workspace_id != workspace_id:
            raise HTTPException(404, 'Запись не найдена')
    if db.info.get('guest'):
        for model, limit in LIMITS.items():
            added=sum(isinstance(obj,model) for obj in db.new)
            if added and db.scalar(select(func.count()).select_from(model).where(model.workspace_id==workspace_id))+added > limit:
                raise HTTPException(422,'Достигнут лимит записей в демонстрации. Начните новое демо в профиле.')
