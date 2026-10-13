from sqlalchemy import select, func, or_
from .models import Group, Teacher, Room, Subject, User, Schedule, Lesson, Series, Audit
from .records import record, owned
from app.domain.lesson_policy import snapshot

class ScheduleRepository:
    def __init__(self, db): self.db = db

    def list_schedules(self, context):
        query = select(Schedule).where(Schedule.workspace_id==context.workspace_id).order_by(Schedule.id.desc())
        if not context.can_edit: query = query.where(Schedule.status=='published')
        return [record(x) for x in self.db.scalars(query)]

    def get_schedule(self, context, ident): return record(owned(self.db,Schedule,context,ident))

    def create_schedule(self, context, values):
        obj = Schedule(workspace_id=context.workspace_id, **values)
        self.db.add(obj); self.db.flush()
        return record(obj)

    def has_lessons(self, context, ident):
        return self.db.scalar(select(Lesson.id).where(Lesson.workspace_id==context.workspace_id,Lesson.schedule_id==ident,Lesson.status!='cancelled').limit(1)) is not None

    def publish_schedule(self, context, ident):
        obj = owned(self.db, Schedule, context, ident)
        obj.status = 'published'; self.db.flush()
        return record(obj)

    def list_lessons(self, context, begin, finish, filters, offset, limit):
        query = select(Lesson).join(Schedule,(Lesson.schedule_id==Schedule.id)&(Schedule.workspace_id==context.workspace_id)).where(Lesson.workspace_id==context.workspace_id,Lesson.starts>=begin,Lesson.starts<finish)
        if not context.can_edit: query = query.where(Schedule.status=='published')
        for key,value in filters.items():
            if value is not None: query = query.where(getattr(Lesson,key)==value)
        total = self.db.scalar(select(func.count()).select_from(query.subquery()))
        joined = query.add_columns(Group.name,Teacher.name,Room.name,Subject.name,Schedule.status)
        for model,field in [(Group,'group_id'),(Teacher,'teacher_id'),(Room,'room_id'),(Subject,'subject_id')]:
            joined = joined.join(model,(getattr(Lesson,field)==model.id)&(model.workspace_id==context.workspace_id))
        items = []
        for item,group,teacher,room,subject,status in self.db.execute(joined.order_by(Lesson.starts,Lesson.id).offset(offset).limit(limit)):
            items.append(snapshot(record(item)) | {'group':group,'teacher':teacher,'room':room,'subject':subject,'schedule_status':status})
        return {'items':items,'total':total,'offset':offset,'limit':limit}

    def get_lesson(self, context, ident): return record(owned(self.db,Lesson,context,ident))

    def conflicts(self, context, data, exclude_id=None):
        query = select(Lesson).where(Lesson.workspace_id==context.workspace_id,Lesson.status!='cancelled',Lesson.starts<data.ends,Lesson.ends>data.starts,or_(Lesson.group_id==data.group_id,Lesson.teacher_id==data.teacher_id,Lesson.room_id==data.room_id))
        if exclude_id: query = query.where(Lesson.id!=exclude_id)
        return [{'lesson_id':obj.id,'starts':obj.starts.isoformat(),'ends':obj.ends.isoformat(),'resources':[label for key,label in [('group_id','Группа'),('teacher_id','Преподаватель'),('room_id','Аудитория')] if getattr(data,key)==getattr(obj,key)]} for obj in self.db.scalars(query.order_by(Lesson.starts,Lesson.id))]

    def insert_lesson(self, context, values):
        obj = Lesson(workspace_id=context.workspace_id, **values)
        self.db.add(obj); self.db.flush()
        return record(obj)

    def update_lesson(self, context, ident, values):
        obj = owned(self.db,Lesson,context,ident)
        for key,value in values.items(): setattr(obj,key,value)
        self.db.flush()
        return record(obj)

    def append_audit(self, context, action, lesson=None, schedule_id=None, before=None, reason=''):
        self.db.add(Audit(workspace_id=context.workspace_id,actor_id=context.user_id,action=action,lesson_id=lesson['id'] if lesson else None,schedule_id=lesson['schedule_id'] if lesson else schedule_id,before=before or {},after=snapshot(lesson) if lesson else {},reason=reason))

    def history(self, context, ident):
        query = select(Audit,User.name).join(User,(User.id==Audit.actor_id)&(User.workspace_id==context.workspace_id)).where(Audit.workspace_id==context.workspace_id,Audit.lesson_id==ident).order_by(Audit.id.desc())
        return [{'id':a.id,'action':a.action,'reason':a.reason,'created':a.created,'before':a.before,'after':a.after,'actor':name if context.can_edit else 'Диспетчер'} for a,name in self.db.execute(query)]

    def find_series(self, context, request_key):
        return record(self.db.scalar(select(Series).where(Series.workspace_id==context.workspace_id,Series.author_id==context.user_id,Series.request_key==request_key)))

    def create_series(self, context, request_key, digest):
        obj = Series(workspace_id=context.workspace_id,author_id=context.user_id,request_key=request_key,payload_hash=digest)
        self.db.add(obj); self.db.flush()
        return record(obj)

    def series_lessons(self, context, ident):
        return list(self.db.scalars(select(Lesson.id).where(Lesson.workspace_id==context.workspace_id,Lesson.series_id==ident).order_by(Lesson.id)))
