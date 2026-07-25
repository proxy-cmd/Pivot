"""create PostgreSQL application schema

Revision ID: 20260725_01
Revises:
Create Date: 2026-07-25
"""

from alembic import op
import sqlalchemy as sa

revision = '20260725_01'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('users', sa.Column('id', sa.String(32), primary_key=True), sa.Column('google_id', sa.String(255), nullable=False, unique=True), sa.Column('email', sa.String(320), nullable=False, unique=True), sa.Column('full_name', sa.String(255), nullable=False), sa.Column('avatar_url', sa.Text()), sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column('last_login', sa.DateTime(timezone=True), nullable=False))
    op.create_table('datasets', sa.Column('id', sa.String(32), primary_key=True), sa.Column('owner_user_id', sa.String(32), sa.ForeignKey('users.id'), nullable=False), sa.Column('name', sa.String(500), nullable=False), sa.Column('source_path', sa.Text(), nullable=False), sa.Column('active_path', sa.Text()), sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column('profile', sa.Text()), sa.Column('status', sa.String(50)))
    op.create_table('refresh_sessions', sa.Column('id', sa.String(32), primary_key=True), sa.Column('user_id', sa.String(32), sa.ForeignKey('users.id'), nullable=False), sa.Column('token_hash', sa.String(64), nullable=False, unique=True), sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False), sa.Column('user_agent', sa.String(500)), sa.Column('ip_address', sa.String(64)), sa.Column('parent_id', sa.String(32)), sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column('revoked_at', sa.DateTime(timezone=True)))
    for table, extra in [('versions', [sa.Column('number', sa.Integer(), nullable=False), sa.Column('parent_id', sa.String(32)), sa.Column('operation', sa.String(100), nullable=False), sa.Column('detail', sa.Text(), nullable=False), sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)]), ('chunks', [sa.Column('source', sa.String(500), nullable=False), sa.Column('content', sa.Text(), nullable=False), sa.Column('metadata', sa.Text(), nullable=False)]), ('events', [sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True), sa.Column('kind', sa.String(100), nullable=False), sa.Column('message', sa.Text(), nullable=False), sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)]), ('transformations', [sa.Column('id', sa.String(32), primary_key=True), sa.Column('operation', sa.String(100), nullable=False), sa.Column('status', sa.String(50), nullable=False), sa.Column('preview_path', sa.Text(), nullable=False), sa.Column('metrics', sa.Text(), nullable=False), sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column('resolved_at', sa.DateTime(timezone=True))]), ('reports', [sa.Column('id', sa.String(32), primary_key=True), sa.Column('title', sa.String(120), nullable=False), sa.Column('format', sa.String(20), nullable=False), sa.Column('path', sa.Text(), nullable=False), sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)])]:
        columns = ([] if table in ('events', 'transformations', 'reports') else [sa.Column('id', sa.String(32), primary_key=True)]) + [sa.Column('dataset_id', sa.String(32), sa.ForeignKey('datasets.id'), nullable=False), sa.Column('owner_user_id', sa.String(32), sa.ForeignKey('users.id'), nullable=False)] + extra
        if table == 'versions':
            columns.append(sa.UniqueConstraint('dataset_id', 'number', name='uq_versions_dataset_number'))
        op.create_table(table, *columns)
        op.create_index(f'ix_{table}_owner_dataset', table, ['owner_user_id', 'dataset_id'])
    op.create_index('ix_datasets_owner_user_id', 'datasets', ['owner_user_id'])
    op.create_index('ix_refresh_sessions_user_id', 'refresh_sessions', ['user_id'])


def downgrade() -> None:
    for table in ('reports', 'transformations', 'events', 'chunks', 'versions', 'refresh_sessions', 'datasets', 'users'):
        op.drop_table(table)
