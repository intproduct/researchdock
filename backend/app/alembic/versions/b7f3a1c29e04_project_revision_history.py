"""project_revision_history

Revision ID: b7f3a1c29e04
Revises: d42026f707b5
Create Date: 2026-09-19 10:30:00.000000

"""
import uuid
from datetime import UTC, datetime

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = 'b7f3a1c29e04'
down_revision = 'd42026f707b5'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('projectrevision',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('project_id', sa.Uuid(), nullable=False),
    sa.Column('revision', sa.Integer(), nullable=False),
    sa.Column('snapshot', sa.JSON(), nullable=False),
    sa.Column('actor_id', sa.Uuid(), nullable=True),
    sa.Column('origin', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
    sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('project_updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['actor_id'], ['user.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['project_id'], ['project.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('project_id', 'revision', name='uq_project_revision')
    )
    op.create_index(op.f('ix_projectrevision_project_id'), 'projectrevision', ['project_id'], unique=False)

    # Backfill exactly one migrated_baseline snapshot per existing project, at
    # its current revision. recorded_at is the migration time, not the original
    # edit time; project_updated_at keeps the project's real last update, and
    # the missing 1..N-1 revisions are left absent instead of invented.
    connection = op.get_bind()
    project = sa.table(
        "project",
        sa.column("id", sa.Uuid()),
        sa.column("name", sa.String()),
        sa.column("description", sa.String()),
        sa.column("stage", sa.String()),
        sa.column("status_note", sa.String()),
        sa.column("next_step", sa.String()),
        sa.column("revision", sa.Integer()),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    revision_table = sa.table(
        "projectrevision",
        sa.column("id", sa.Uuid()),
        sa.column("project_id", sa.Uuid()),
        sa.column("revision", sa.Integer()),
        sa.column("snapshot", sa.JSON()),
        sa.column("actor_id", sa.Uuid()),
        sa.column("origin", sa.String()),
        sa.column("recorded_at", sa.DateTime(timezone=True)),
        sa.column("project_updated_at", sa.DateTime(timezone=True)),
    )
    already_recorded = set(
        connection.execute(sa.select(revision_table.c.project_id).distinct()).scalars()
    )
    recorded_at = datetime.now(UTC)
    rows = [
        {
            "id": uuid.uuid4(),
            "project_id": row.id,
            "revision": row.revision,
            "snapshot": {
                "name": row.name,
                "description": row.description,
                "stage": row.stage,
                "status_note": row.status_note,
                "next_step": row.next_step,
            },
            "actor_id": None,
            "origin": "migrated_baseline",
            "recorded_at": recorded_at,
            "project_updated_at": row.updated_at,
        }
        for row in connection.execute(sa.select(project)).all()
        if row.id not in already_recorded
    ]
    if rows:
        connection.execute(sa.insert(revision_table), rows)


def downgrade():
    op.drop_index(op.f('ix_projectrevision_project_id'), table_name='projectrevision')
    op.drop_table('projectrevision')
