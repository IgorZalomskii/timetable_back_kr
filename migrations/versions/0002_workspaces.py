"""Preserve legacy data and add isolated visitor workspaces."""
from alembic import op
import sqlalchemy as sa

revision = '0002'
down_revision = '0001'
TABLES = ('groups','teachers','subjects','rooms','users','periods','schedules','series','lessons','audit')
REFS = {
    'users': [('group_id','groups'),('teacher_id','teachers')],
    'schedules': [('period_id','periods'),('author_id','users')],
    'series': [('author_id','users')],
    'lessons': [('schedule_id','schedules'),('group_id','groups'),('teacher_id','teachers'),('room_id','rooms'),('subject_id','subjects'),('series_id','series')],
    'audit': [('lesson_id','lessons'),('schedule_id','schedules'),('actor_id','users')],
}

def upgrade():
    op.create_table('workspaces', sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('kind', sa.String(20), nullable=False),
        sa.Column('created', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('expires', sa.DateTime(timezone=True)),
        sa.CheckConstraint("kind IN ('legacy','demo')"))
    op.create_index('ix_workspaces_expires','workspaces',['expires'])
    op.execute("INSERT INTO workspaces (id,kind) VALUES (1,'legacy')")
    op.execute("SELECT setval(pg_get_serial_sequence('workspaces','id'),1,true)")
    for table in TABLES:
        op.add_column(table, sa.Column('workspace_id',sa.Integer(),nullable=False,server_default='1'))
        op.create_foreign_key(f'{table}_workspace_fk',table,'workspaces',['workspace_id'],['id'],ondelete='CASCADE')
        op.create_index(f'ix_{table}_workspace_id',table,['workspace_id'])
        op.create_unique_constraint(f'{table}_workspace_id_id_key',table,['workspace_id','id'])
        op.alter_column(table,'workspace_id',server_default=None)
    for table in ('groups','teachers','subjects','rooms'):
        op.drop_constraint(f'{table}_name_key',table,type_='unique')
        op.create_unique_constraint(f'{table}_workspace_name_key',table,['workspace_id','name'])
    op.add_column('users',sa.Column('is_guest',sa.Boolean(),nullable=False,server_default=sa.false()))
    for table, refs in REFS.items():
        for column, target in refs:
            op.create_foreign_key(f'{table}_{column}_workspace_fk',table,target,
                ['workspace_id',column],['workspace_id','id'])

def downgrade():
    raise RuntimeError('Do not run old unscoped code against guest data. Restore the pre-release database backup into a separate database for rollback.')
