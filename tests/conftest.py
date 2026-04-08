from datetime import datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models as models
import app.routes as routes
from app.db import get_db
from app.main import app
from app.models import Client, Project, Task


class FrozenDateTime(datetime):
    current = datetime(2026, 4, 8, 9, 0, 0)

    @classmethod
    def now(cls, tz=None):
        if tz is not None:
            return tz.fromutc(cls.current.replace(tzinfo=tz))
        return cls.current


@pytest.fixture
def frozen_time(monkeypatch):
    monkeypatch.setattr(routes, "datetime", FrozenDateTime)
    monkeypatch.setattr(models, "datetime", FrozenDateTime)
    return FrozenDateTime


@pytest.fixture
def session_factory(tmp_path):
    db_path = tmp_path / "test.db"
    alembic_config = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    alembic_config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(alembic_config, "head")

    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    yield SessionLocal

    engine.dispose()


@pytest.fixture
def client(session_factory):
    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def project_task_ids(session_factory):
    session = session_factory()
    try:
        client = Client(name="Acme")
        session.add(client)
        session.flush()

        project = Project(client_id=client.id, name="Website")
        session.add(project)
        session.flush()

        task = Task(project_id=project.id, name="Build timer")
        session.add(task)
        session.commit()

        return {"client_id": client.id, "project_id": project.id, "task_id": task.id}
    finally:
        session.close()
