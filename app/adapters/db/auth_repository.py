from sqlalchemy import select, delete
from .models import Session, User, Workspace
from .records import record, owned
from app.domain.values import SystemContext

class AuthRepository:
    def __init__(self, db): self.db = db

    def session_identity(self, scope, token_hash):
        assert isinstance(scope,SystemContext)
        session = self.db.get(Session, token_hash)
        if session is None: return None
        user = self.db.get(User,session.user_id)
        workspace = self.db.get(Workspace,user.workspace_id) if user else None
        return record(user,True),record(session,True),record(workspace,True)

    def find_user(self, scope, username):
        assert isinstance(scope,SystemContext)
        return record(self.db.scalar(select(User).where(User.username==username)),True)

    def lock_user(self, context):
        obj = self.db.scalar(select(User).where(User.workspace_id==context.workspace_id,User.id==context.user_id).with_for_update().execution_options(populate_existing=True))
        return record(obj,True)

    def update_profile(self, context, values):
        obj = owned(self.db,User,context,context.user_id)
        for key,value in values.items(): setattr(obj,key,value)
        self.db.flush()
        return record(obj,True)

    def create_session(self, context, values):
        owned(self.db,User,context,context.user_id)
        obj = Session(**values)
        self.db.add(obj); self.db.flush()
        return record(obj,True)

    def cap_sessions(self, context, old_hash, now):
        # Only sessions belonging to this explicitly scoped account are mutated.
        owned(self.db,User,context,context.user_id)
        self.db.execute(delete(Session).where(Session.user_id==context.user_id, (Session.token_hash==old_hash)|(Session.expires<now)))
        excess = list(self.db.scalars(select(Session.token_hash).where(Session.user_id==context.user_id).order_by(Session.expires.desc()).offset(4)))
        if excess: self.db.execute(delete(Session).where(Session.user_id==context.user_id,Session.token_hash.in_(excess)))

    def delete_session(self, context, token_hash):
        owned(self.db,User,context,context.user_id)
        self.db.execute(delete(Session).where(Session.user_id==context.user_id,Session.token_hash==token_hash))
