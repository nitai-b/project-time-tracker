"""initial schema

Revision ID: 20260408_0001
Revises:
Create Date: 2026-04-08 00:00:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260408_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "clients" not in existing_tables:
        op.create_table(
            "clients",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("name"),
        )

    if "projects" not in existing_tables:
        op.create_table(
            "projects",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("client_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["client_id"], ["clients.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("client_id", "name", name="uq_project_client_name"),
        )

    if "tasks" not in existing_tables:
        op.create_table(
            "tasks",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("project_id", "name", name="uq_task_project_name"),
        )

    if "time_entries" not in existing_tables:
        op.create_table(
            "time_entries",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("task_id", sa.Integer(), nullable=False),
            sa.Column("start_time", sa.DateTime(), nullable=False),
            sa.Column("end_time", sa.DateTime(), nullable=True),
            sa.Column("paused_at", sa.DateTime(), nullable=True),
            sa.Column("paused_seconds", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
            sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    else:
        time_entry_columns = {column["name"] for column in inspector.get_columns("time_entries")}
        if "paused_at" not in time_entry_columns:
            op.add_column("time_entries", sa.Column("paused_at", sa.DateTime(), nullable=True))
        if "paused_seconds" not in time_entry_columns:
            op.add_column(
                "time_entries",
                sa.Column("paused_seconds", sa.Integer(), nullable=False, server_default="0"),
            )

    index_map = {
        "projects": {"ix_projects_client_id"},
        "tasks": {"ix_tasks_project_id"},
        "time_entries": {
            "ix_time_entries_project_id",
            "ix_time_entries_task_id",
            "ix_time_entries_start_time",
        },
    }
    existing_indexes = {
        table_name: {index["name"] for index in inspector.get_indexes(table_name)}
        for table_name in index_map
        if table_name in set(inspector.get_table_names())
    }

    if "projects" in existing_indexes and "ix_projects_client_id" not in existing_indexes["projects"]:
        op.create_index(op.f("ix_projects_client_id"), "projects", ["client_id"], unique=False)
    if "tasks" in existing_indexes and "ix_tasks_project_id" not in existing_indexes["tasks"]:
        op.create_index(op.f("ix_tasks_project_id"), "tasks", ["project_id"], unique=False)
    if "time_entries" in existing_indexes:
        if "ix_time_entries_project_id" not in existing_indexes["time_entries"]:
            op.create_index(op.f("ix_time_entries_project_id"), "time_entries", ["project_id"], unique=False)
        if "ix_time_entries_task_id" not in existing_indexes["time_entries"]:
            op.create_index(op.f("ix_time_entries_task_id"), "time_entries", ["task_id"], unique=False)
        if "ix_time_entries_start_time" not in existing_indexes["time_entries"]:
            op.create_index(op.f("ix_time_entries_start_time"), "time_entries", ["start_time"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_time_entries_start_time"), table_name="time_entries")
    op.drop_index(op.f("ix_time_entries_task_id"), table_name="time_entries")
    op.drop_index(op.f("ix_time_entries_project_id"), table_name="time_entries")
    op.drop_table("time_entries")
    op.drop_index(op.f("ix_tasks_project_id"), table_name="tasks")
    op.drop_table("tasks")
    op.drop_index(op.f("ix_projects_client_id"), table_name="projects")
    op.drop_table("projects")
    op.drop_table("clients")
