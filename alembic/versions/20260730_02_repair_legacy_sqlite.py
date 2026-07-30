"""repair ownership columns in legacy local SQLite databases

Revision ID: 20260730_02
Revises: 20260725_01
Create Date: 2026-07-30
"""

from alembic import op
import sqlalchemy as sa


revision = '20260730_02'
down_revision = '20260725_01'
branch_labels = None
depends_on = None


TABLES = ('versions', 'chunks', 'events', 'transformations', 'reports')


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    for table in TABLES:
        columns = {column['name'] for column in inspector.get_columns(table)}
        if 'owner_user_id' not in columns:
            op.add_column(table, sa.Column('owner_user_id', sa.String(32), nullable=True))
            connection.execute(sa.text(
                f'UPDATE {table} SET owner_user_id = '
                '(SELECT owner_user_id FROM datasets WHERE datasets.id = ' + table + '.dataset_id) '
                'WHERE owner_user_id IS NULL'
            ))
            op.create_index(f'ix_{table}_owner_dataset', table, ['owner_user_id', 'dataset_id'])


def downgrade() -> None:
    # SQLite cannot safely remove columns in place. This repair is intentionally irreversible.
    pass
