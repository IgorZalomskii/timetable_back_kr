"""Initial schedule schema."""
from alembic import op
from pathlib import Path

revision = '0001'
down_revision = None

def upgrade():
    op.execute('CREATE EXTENSION IF NOT EXISTS btree_gist')
    # Frozen DDL: later model edits cannot silently change an old migration.
    for statement in Path(__file__).with_name('0001_schema.sql').read_text(encoding='utf-8').split(';'):
        if statement.strip():
            op.execute(statement)

def downgrade():
    for table in ('audit','lessons','series','schedules','sessions','users','periods','subjects','rooms','teachers','groups','login_attempts'):
        op.drop_table(table)
