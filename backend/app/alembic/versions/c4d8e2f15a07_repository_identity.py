"""repository_identity

Revision ID: c4d8e2f15a07
Revises: b7f3a1c29e04
Create Date: 2026-09-21 00:00:00.000000

Adds the Repository identity entity and the WorkingCopy binding fields.

- New table ``repository``: logical, per-project repository identity keyed by a
  server-generated UUID. The name is a display label; duplicate names are
  allowed and never used to merge. No remote_url / platform fields.
- ``workingcopy.repository_id`` (nullable): null means "uncategorized", not a
  default repository.
- ``workingcopy.binding_revision`` (non-null, default 0): optimistic-concurrency
  counter for the binding only. Existing copies migrate to 0 (uncategorized).

A composite foreign key ``(repository_id, project_id) -> repository(id,
project_id)`` guarantees a copy can only bind a repository of its own project,
enforced by the database rather than by filtering in application code. No
Repository rows are auto-created for existing projects, and no clustering by
remote/name is performed.
"""
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op

# revision identifiers, used by Alembic.
revision = 'c4d8e2f15a07'
down_revision = 'b7f3a1c29e04'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'repository',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('project_id', sa.Uuid(), nullable=False),
        sa.Column('name', sqlmodel.sql.sqltypes.AutoString(length=120), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['project.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('id', 'project_id', name='uq_repository_id_project'),
    )
    op.create_index(
        op.f('ix_repository_project_id'), 'repository', ['project_id'], unique=False
    )

    # Batch mode recreates the table so SQLite picks up the new composite FK and
    # the SET NULL rule; on PostgreSQL it maps to plain ALTER TABLE.
    with op.batch_alter_table('workingcopy') as batch_op:
        batch_op.add_column(sa.Column('repository_id', sa.Uuid(), nullable=True))
        batch_op.add_column(
            sa.Column('binding_revision', sa.Integer(), nullable=False, server_default='0')
        )
        batch_op.create_index(
            op.f('ix_workingcopy_repository_id'), ['repository_id'], unique=False
        )
        batch_op.create_foreign_key(
            'fk_copy_repository_project',
            'repository',
            ['repository_id', 'project_id'],
            ['id', 'project_id'],
            ondelete='SET NULL',
        )


def downgrade():
    # Dropping the binding metadata loses the new association data, but existing
    # projects, copies, observations and T01 history are preserved. Restoring
    # associations requires a full backup; production data is never auto-reverted.
    with op.batch_alter_table('workingcopy') as batch_op:
        batch_op.drop_constraint('fk_copy_repository_project', type_='foreignkey')
        batch_op.drop_index(op.f('ix_workingcopy_repository_id'))
        batch_op.drop_column('binding_revision')
        batch_op.drop_column('repository_id')
    op.drop_index(op.f('ix_repository_project_id'), table_name='repository')
    op.drop_table('repository')
