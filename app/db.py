from pathlib import Path

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import DeclarativeBase, sessionmaker


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
DATABASE_URL = f"sqlite:///{DATA_DIR / 'time_tracker.db'}"


class Base(DeclarativeBase):
    pass


engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def ensure_time_entry_schema() -> None:
    inspector = inspect(engine)
    if "time_entries" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("time_entries")}
    with engine.begin() as connection:
        if "paused_at" not in columns:
            connection.exec_driver_sql("ALTER TABLE time_entries ADD COLUMN paused_at DATETIME")
        if "paused_seconds" not in columns:
            connection.exec_driver_sql(
                "ALTER TABLE time_entries ADD COLUMN paused_seconds INTEGER NOT NULL DEFAULT 0"
            )


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
