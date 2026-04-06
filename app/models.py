from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)


class Client(TimestampMixin, Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    projects: Mapped[list["Project"]] = relationship(
        back_populates="client", cascade="all, delete-orphan"
    )


class Project(TimestampMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("client_id", "name", name="uq_project_client_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    client: Mapped["Client"] = relationship(back_populates="projects")
    tasks: Mapped[list["Task"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    time_entries: Mapped[list["TimeEntry"]] = relationship(back_populates="project")


class Task(TimestampMixin, Base):
    __tablename__ = "tasks"
    __table_args__ = (UniqueConstraint("project_id", "name", name="uq_task_project_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    project: Mapped["Project"] = relationship(back_populates="tasks")
    time_entries: Mapped[list["TimeEntry"]] = relationship(back_populates="task")


class TimeEntry(TimestampMixin, Base):
    __tablename__ = "time_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), nullable=False, index=True)
    start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    end_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    paused_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    project: Mapped["Project"] = relationship(back_populates="time_entries")
    task: Mapped["Task"] = relationship(back_populates="time_entries")

    @property
    def is_paused(self) -> bool:
        return self.end_time is None and self.paused_at is not None

    @property
    def is_running(self) -> bool:
        return self.end_time is None and self.paused_at is None

    def effective_end(self, now: datetime | None = None) -> datetime:
        if self.end_time is not None:
            return self.end_time
        if self.paused_at is not None:
            return self.paused_at
        return now or datetime.now()

    @property
    def duration_seconds(self) -> int | None:
        if self.end_time is None and self.paused_at is None:
            return None
        elapsed = int((self.effective_end() - self.start_time).total_seconds()) - self.paused_seconds
        return max(elapsed, 0)
