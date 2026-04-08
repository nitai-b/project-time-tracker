from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_alembic_upgrade_adds_pause_columns_to_existing_time_entries_table(tmp_path):
    db_path = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})

    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE clients (
                id INTEGER NOT NULL PRIMARY KEY,
                name VARCHAR(255) NOT NULL UNIQUE,
                created_at DATETIME NOT NULL
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE projects (
                id INTEGER NOT NULL PRIMARY KEY,
                client_id INTEGER NOT NULL,
                name VARCHAR(255) NOT NULL,
                created_at DATETIME NOT NULL,
                CONSTRAINT uq_project_client_name UNIQUE (client_id, name),
                FOREIGN KEY(client_id) REFERENCES clients (id)
            )
            """
        )
        connection.exec_driver_sql(
            "CREATE INDEX ix_projects_client_id ON projects (client_id)"
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE tasks (
                id INTEGER NOT NULL PRIMARY KEY,
                project_id INTEGER NOT NULL,
                name VARCHAR(255) NOT NULL,
                created_at DATETIME NOT NULL,
                CONSTRAINT uq_task_project_name UNIQUE (project_id, name),
                FOREIGN KEY(project_id) REFERENCES projects (id)
            )
            """
        )
        connection.exec_driver_sql("CREATE INDEX ix_tasks_project_id ON tasks (project_id)")
        connection.exec_driver_sql(
            """
            CREATE TABLE time_entries (
                id INTEGER NOT NULL PRIMARY KEY,
                project_id INTEGER NOT NULL,
                task_id INTEGER NOT NULL,
                start_time DATETIME NOT NULL,
                end_time DATETIME,
                notes TEXT,
                created_at DATETIME NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects (id),
                FOREIGN KEY(task_id) REFERENCES tasks (id)
            )
            """
        )
        connection.exec_driver_sql("CREATE INDEX ix_time_entries_project_id ON time_entries (project_id)")
        connection.exec_driver_sql("CREATE INDEX ix_time_entries_task_id ON time_entries (task_id)")
        connection.exec_driver_sql("CREATE INDEX ix_time_entries_start_time ON time_entries (start_time)")

    alembic_config = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    alembic_config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(alembic_config, "head")

    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("time_entries")}

    assert "paused_at" in columns
    assert "paused_seconds" in columns
    assert "alembic_version" in set(inspector.get_table_names())

    engine.dispose()
