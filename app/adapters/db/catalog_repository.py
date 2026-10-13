from sqlalchemy import select, delete
from .models import Group, Teacher, Room, Subject, User, Session, Period, Lesson
from .records import record, owned

DIRECTORIES = {'groups':Group,'teachers':Teacher,'rooms':Room,'subjects':Subject}

class CatalogRepository:
    def __init__(self, db): self.db = db

    def list_directory(self, context, kind):
        model = DIRECTORIES[kind]
        return [record(x) for x in self.db.scalars(select(model).where(model.workspace_id==context.workspace_id).order_by(model.name))]

    def get_directory(self, context, kind, ident):
        model = DIRECTORIES[kind]
        if ident is not None: return record(owned(self.db, model, context, ident))
        return record(self.db.scalar(select(model).where(model.workspace_id==context.workspace_id, model.active==True).order_by(model.id).limit(1)))

    def create_directory(self, context, kind, values):
        model = DIRECTORIES[kind]
        obj = model(workspace_id=context.workspace_id, **{key:value for key,value in values.items() if key in model.__table__.columns})
        self.db.add(obj); self.db.flush()
        return record(obj)

    def update_directory(self, context, kind, ident, values):
        model = DIRECTORIES[kind]
        obj = owned(self.db, model, context, ident)
        for key,value in values.items():
            if key in model.__table__.columns: setattr(obj,key,value)
        self.db.flush()
        return record(obj)

    def future_resources(self, context, kind, ident, now):
        field = {'groups':'group_id','teachers':'teacher_id','rooms':'room_id','subjects':'subject_id'}[kind]
        query = select(Group.size,Room.capacity).select_from(Lesson).join(Group, (Lesson.group_id==Group.id)&(Group.workspace_id==context.workspace_id)).join(Room,(Lesson.room_id==Room.id)&(Room.workspace_id==context.workspace_id)).where(Lesson.workspace_id==context.workspace_id, getattr(Lesson,field)==ident, Lesson.ends>now, Lesson.status!='cancelled')
        return [dict(row._mapping) for row in self.db.execute(query)]

    def list_users(self, context):
        return [record(x,True) for x in self.db.scalars(select(User).where(User.workspace_id==context.workspace_id).order_by(User.id))]

    def create_user(self, context, values):
        obj = User(workspace_id=context.workspace_id, **values)
        self.db.add(obj); self.db.flush()
        return record(obj,True)

    def toggle_user(self, context, ident):
        obj = owned(self.db, User, context, ident)
        obj.active = not obj.active
        self.db.execute(delete(Session).where(Session.user_id==obj.id))
        self.db.flush()
        return record(obj,True)

    def list_periods(self, context):
        return [record(x) for x in self.db.scalars(select(Period).where(Period.workspace_id==context.workspace_id).order_by(Period.start.desc()))]

    def get_period(self, context, ident): return record(owned(self.db,Period,context,ident))

    def create_period(self, context, values):
        obj = Period(workspace_id=context.workspace_id, **values)
        self.db.add(obj); self.db.flush()
        return record(obj)
