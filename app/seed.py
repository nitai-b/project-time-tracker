from datetime import datetime

from sqlalchemy import select

from app.db import Base, SessionLocal, engine
from app.models import Client, Project, Task


def seed_example_data() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        client = db.scalar(select(Client).where(Client.name == "SHP"))
        if client is None:
            client = Client(name="SHP")
            db.add(client)
            db.flush()

        project = db.scalar(
            select(Project).where(
                Project.client_id == client.id, Project.name == "New Tech Stack Implementation"
            )
        )
        if project is None:
            project = Project(client_id=client.id, name="New Tech Stack Implementation")
            db.add(project)
            db.flush()

        task = db.scalar(
            select(Task).where(
                Task.project_id == project.id, Task.name == "Zapier Automations Porting to Python"
            )
        )
        if task is None:
            db.add(Task(project_id=project.id, name="Zapier Automations Porting to Python"))

        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    seed_example_data()
    print(f"Seed data ensured at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
