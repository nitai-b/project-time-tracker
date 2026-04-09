"""add soft delete columns

Revision ID: 20260408_0002
Revises: 20260408_0001
Create Date: 2026-04-08 00:30:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260408_0002"
down_revision: Union[str, None] = "20260408_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def add_deleted_at_column(table_name: str) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns(table_name)}
    indexes = {index["name"] for index in inspector.get_indexes(table_name)}

    if "deleted_at" not in columns:
        op.add_column(table_name, sa.Column("deleted_at", sa.DateTime(), nullable=True))

    index_name = f"ix_{table_name}_deleted_at"
    if index_name not in indexes:
        op.create_index(index_name, table_name, ["deleted_at"], unique=False)


def upgrade() -> None:
    for table_name in ("clients", "projects", "tasks", "time_entries"):
        add_deleted_at_column(table_name)


def downgrade() -> None:
    for table_name in ("time_entries", "tasks", "projects", "clients"):
        op.drop_index(f"ix_{table_name}_deleted_at", table_name=table_name)
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_column("deleted_at")
