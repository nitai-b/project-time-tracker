import csv
import io
from datetime import date, datetime, time, timedelta
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.db import get_db
from app.models import Client, Project, Task, TimeEntry


router = APIRouter()


def parse_optional_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid filter value.") from exc


def parse_datetime_local(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid date/time value.") from exc


def format_duration(seconds: int | None) -> str:
    if seconds is None:
        return "Running"
    hours, remainder = divmod(max(seconds, 0), 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def friendly_datetime(value: datetime | None) -> str:
    if value is None:
        return "-"
    return value.strftime("%Y-%m-%d %H:%M:%S")


def datetime_input_value(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.strftime("%Y-%m-%dT%H:%M:%S")


def redirect_with_message(path: str, message: str, level: str = "info") -> RedirectResponse:
    query = urlencode({"message": message, "level": level})
    return RedirectResponse(url=f"{path}?{query}", status_code=303)


def get_active_entry(db: Session) -> TimeEntry | None:
    return db.scalar(
        select(TimeEntry)
        .options(joinedload(TimeEntry.project).joinedload(Project.client), joinedload(TimeEntry.task))
        .where(TimeEntry.end_time.is_(None))
        .order_by(TimeEntry.start_time.desc())
    )


def get_form_data(db: Session) -> dict[str, Any]:
    clients = db.scalars(select(Client).order_by(Client.name)).all()
    projects = db.scalars(select(Project).options(joinedload(Project.client)).order_by(Project.name)).all()
    tasks = db.scalars(select(Task).options(joinedload(Task.project)).order_by(Task.name)).all()
    return {"clients": clients, "projects": projects, "tasks": tasks}


def validate_project_task(db: Session, project_id: int, task_id: int) -> tuple[Project, Task]:
    project = db.get(Project, project_id)
    task = db.get(Task, task_id)
    if not project or not task:
        raise HTTPException(status_code=404, detail="Project or task not found.")
    if task.project_id != project.id:
        raise HTTPException(status_code=400, detail="Selected task does not belong to the selected project.")
    return project, task


def compute_range_totals(db: Session, start: datetime, end: datetime) -> int:
    entries = db.scalars(
        select(TimeEntry).where(TimeEntry.start_time >= start, TimeEntry.start_time < end)
    ).all()
    total = 0
    now = datetime.now()
    for entry in entries:
        effective_end = entry.end_time or now
        total += max(int((effective_end - entry.start_time).total_seconds()), 0)
    return total


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    active_entry = get_active_entry(db)
    recent_entries = db.scalars(
        select(TimeEntry)
        .options(
            joinedload(TimeEntry.project).joinedload(Project.client),
            joinedload(TimeEntry.task),
        )
        .order_by(TimeEntry.start_time.desc())
        .limit(10)
    ).all()

    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    today_total = compute_range_totals(db, datetime.combine(today, time.min), datetime.combine(today + timedelta(days=1), time.min))
    week_total = compute_range_totals(
        db,
        datetime.combine(week_start, time.min),
        datetime.combine(week_start + timedelta(days=7), time.min),
    )

    context = {
        "request": request,
        "active_entry": active_entry,
        "recent_entries": recent_entries,
        "today_total": today_total,
        "week_total": week_total,
        "form_defaults": {"start_time": datetime_input_value(datetime.now())},
        **get_form_data(db),
    }
    return request.app.state.templates.TemplateResponse("dashboard.html", context)


@router.get("/clients", response_class=HTMLResponse)
def list_clients(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    clients = db.scalars(select(Client).order_by(Client.name)).all()
    return request.app.state.templates.TemplateResponse(
        "clients.html", {"request": request, "clients": clients}
    )


@router.post("/clients")
def create_client(name: str = Form(...), db: Session = Depends(get_db)) -> RedirectResponse:
    clean_name = name.strip()
    if not clean_name:
        return redirect_with_message("/clients", "Client name is required.", "error")
    existing = db.scalar(select(Client).where(func.lower(Client.name) == clean_name.lower()))
    if existing:
        return redirect_with_message("/clients", "Client already exists.", "error")
    db.add(Client(name=clean_name))
    db.commit()
    return redirect_with_message("/clients", "Client created.")


@router.post("/clients/{client_id}/delete")
def delete_client(client_id: int, db: Session = Depends(get_db)) -> RedirectResponse:
    client = db.get(Client, client_id)
    if not client:
        return redirect_with_message("/clients", "Client not found.", "error")
    if client.projects:
        return redirect_with_message(
            "/clients", "Client cannot be deleted while projects still exist.", "error"
        )
    db.delete(client)
    db.commit()
    return redirect_with_message("/clients", "Client deleted.")


@router.get("/projects", response_class=HTMLResponse)
def list_projects(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    projects = db.scalars(select(Project).options(joinedload(Project.client)).order_by(Project.name)).all()
    return request.app.state.templates.TemplateResponse(
        "projects.html",
        {"request": request, "projects": projects, "clients": db.scalars(select(Client).order_by(Client.name)).all()},
    )


@router.post("/projects")
def create_project(
    client_id: int = Form(...), name: str = Form(...), db: Session = Depends(get_db)
) -> RedirectResponse:
    client = db.get(Client, client_id)
    clean_name = name.strip()
    if not client:
        return redirect_with_message("/projects", "Client is required.", "error")
    if not clean_name:
        return redirect_with_message("/projects", "Project name is required.", "error")
    existing = db.scalar(
        select(Project).where(Project.client_id == client.id, func.lower(Project.name) == clean_name.lower())
    )
    if existing:
        return redirect_with_message("/projects", "Project already exists for this client.", "error")
    db.add(Project(client_id=client.id, name=clean_name))
    db.commit()
    return redirect_with_message("/projects", "Project created.")


@router.post("/projects/{project_id}/delete")
def delete_project(project_id: int, db: Session = Depends(get_db)) -> RedirectResponse:
    project = db.get(Project, project_id)
    if not project:
        return redirect_with_message("/projects", "Project not found.", "error")
    has_tasks = db.scalar(select(Task.id).where(Task.project_id == project.id).limit(1))
    has_entries = db.scalar(select(TimeEntry.id).where(TimeEntry.project_id == project.id).limit(1))
    if has_tasks or has_entries:
        return redirect_with_message(
            "/projects",
            "Project cannot be deleted while tasks or time entries still reference it.",
            "error",
        )
    db.delete(project)
    db.commit()
    return redirect_with_message("/projects", "Project deleted.")


@router.get("/tasks", response_class=HTMLResponse)
def list_tasks(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    tasks = db.scalars(
        select(Task).options(joinedload(Task.project).joinedload(Project.client)).order_by(Task.name)
    ).all()
    return request.app.state.templates.TemplateResponse(
        "tasks.html",
        {"request": request, "tasks": tasks, "projects": db.scalars(select(Project).options(joinedload(Project.client)).order_by(Project.name)).all()},
    )


@router.post("/tasks")
def create_task(
    project_id: int = Form(...), name: str = Form(...), db: Session = Depends(get_db)
) -> RedirectResponse:
    project = db.get(Project, project_id)
    clean_name = name.strip()
    if not project:
        return redirect_with_message("/tasks", "Project is required.", "error")
    if not clean_name:
        return redirect_with_message("/tasks", "Task name is required.", "error")
    existing = db.scalar(
        select(Task).where(Task.project_id == project.id, func.lower(Task.name) == clean_name.lower())
    )
    if existing:
        return redirect_with_message("/tasks", "Task already exists for this project.", "error")
    db.add(Task(project_id=project.id, name=clean_name))
    db.commit()
    return redirect_with_message("/tasks", "Task created.")


@router.post("/tasks/{task_id}/delete")
def delete_task(task_id: int, db: Session = Depends(get_db)) -> RedirectResponse:
    task = db.get(Task, task_id)
    if not task:
        return redirect_with_message("/tasks", "Task not found.", "error")
    has_entries = db.scalar(select(TimeEntry.id).where(TimeEntry.task_id == task.id).limit(1))
    if has_entries:
        return redirect_with_message(
            "/tasks", "Task cannot be deleted while time entries still reference it.", "error"
        )
    db.delete(task)
    db.commit()
    return redirect_with_message("/tasks", "Task deleted.")


@router.get("/entries", response_class=HTMLResponse)
def list_entries(
    request: Request,
    client_id: str | None = None,
    project_id: str | None = None,
    task_id: str | None = None,
    entry_date: str | None = None,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    try:
        parsed_client_id = parse_optional_int(client_id)
        parsed_project_id = parse_optional_int(project_id)
        parsed_task_id = parse_optional_int(task_id)
    except HTTPException:
        return redirect_with_message("/entries", "Invalid filter value.", "error")

    stmt = (
        select(TimeEntry)
        .join(TimeEntry.project)
        .join(Project.client)
        .join(TimeEntry.task)
        .options(
            joinedload(TimeEntry.project).joinedload(Project.client),
            joinedload(TimeEntry.task),
        )
        .order_by(TimeEntry.start_time.desc())
    )
    if parsed_client_id:
        stmt = stmt.where(Project.client_id == parsed_client_id)
    if parsed_project_id:
        stmt = stmt.where(TimeEntry.project_id == parsed_project_id)
    if parsed_task_id:
        stmt = stmt.where(TimeEntry.task_id == parsed_task_id)
    if entry_date:
        try:
            chosen_date = date.fromisoformat(entry_date)
        except ValueError:
            return redirect_with_message("/entries", "Invalid date filter.", "error")
        stmt = stmt.where(
            TimeEntry.start_time >= datetime.combine(chosen_date, time.min),
            TimeEntry.start_time < datetime.combine(chosen_date + timedelta(days=1), time.min),
        )

    entries = db.scalars(stmt).all()
    context = {
        "request": request,
        "entries": entries,
        "active_entry": get_active_entry(db),
        "filters": {
            "client_id": parsed_client_id,
            "project_id": parsed_project_id,
            "task_id": parsed_task_id,
            "entry_date": entry_date or "",
        },
        "form_defaults": {
            "start_time": datetime_input_value(datetime.now()),
            "end_time": datetime_input_value(datetime.now()),
        },
        **get_form_data(db),
    }
    return request.app.state.templates.TemplateResponse("time_entries.html", context)


@router.post("/entries/manual")
def create_manual_entry(
    project_id: int = Form(...),
    task_id: int = Form(...),
    start_time: str = Form(...),
    end_time: str = Form(...),
    notes: str = Form(""),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    try:
        start_dt = parse_datetime_local(start_time)
        end_dt = parse_datetime_local(end_time)
    except HTTPException:
        return redirect_with_message("/entries", "Invalid start or end time.", "error")
    if end_dt <= start_dt:
        return redirect_with_message("/entries", "End time must be after start time.", "error")
    try:
        validate_project_task(db, project_id, task_id)
    except HTTPException as exc:
        return redirect_with_message("/entries", exc.detail, "error")
    db.add(
        TimeEntry(
            project_id=project_id,
            task_id=task_id,
            start_time=start_dt,
            end_time=end_dt,
            notes=notes.strip() or None,
        )
    )
    db.commit()
    return redirect_with_message("/entries", "Time entry created.")


@router.post("/entries/start")
def start_entry(
    project_id: int = Form(...),
    task_id: int = Form(...),
    start_time: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    if get_active_entry(db):
        return redirect_with_message("/", "Stop the current running entry first.", "error")
    try:
        validate_project_task(db, project_id, task_id)
    except HTTPException as exc:
        return redirect_with_message("/", exc.detail, "error")
    if not start_time.strip():
        start_dt = datetime.now()
    else:
        try:
            start_dt = parse_datetime_local(start_time)
        except HTTPException:
            return redirect_with_message("/", "Invalid start time.", "error")
    db.add(
        TimeEntry(
            project_id=project_id,
            task_id=task_id,
            start_time=start_dt,
            end_time=None,
            notes=notes.strip() or None,
        )
    )
    db.commit()
    return redirect_with_message("/", "Timer started.")


@router.post("/entries/{entry_id}/stop")
def stop_entry(
    entry_id: int, next_path: str = Form("/"), db: Session = Depends(get_db)
) -> RedirectResponse:
    entry = db.get(TimeEntry, entry_id)
    if not entry:
        return redirect_with_message(next_path or "/", "Time entry not found.", "error")
    if entry.end_time is not None:
        return redirect_with_message(next_path or "/", "Time entry is already stopped.", "error")
    entry.end_time = datetime.now()
    db.commit()
    return redirect_with_message(next_path or "/", "Timer stopped.")


@router.get("/entries/{entry_id}/edit", response_class=HTMLResponse)
def edit_entry_form(request: Request, entry_id: int, db: Session = Depends(get_db)) -> HTMLResponse:
    entry = db.scalar(
        select(TimeEntry)
        .options(
            joinedload(TimeEntry.project).joinedload(Project.client),
            joinedload(TimeEntry.task),
        )
        .where(TimeEntry.id == entry_id)
    )
    if not entry:
        raise HTTPException(status_code=404, detail="Time entry not found.")
    context = {
        "request": request,
        "entry": entry,
        **get_form_data(db),
    }
    return request.app.state.templates.TemplateResponse("time_entry_edit.html", context)


@router.post("/entries/{entry_id}/edit")
def update_entry(
    entry_id: int,
    project_id: int = Form(...),
    task_id: int = Form(...),
    start_time: str = Form(...),
    end_time: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    entry = db.get(TimeEntry, entry_id)
    if not entry:
        return redirect_with_message("/entries", "Time entry not found.", "error")
    try:
        start_dt = parse_datetime_local(start_time)
    except HTTPException:
        return redirect_with_message(f"/entries/{entry_id}/edit", "Invalid start time.", "error")
    end_dt = None
    if end_time.strip():
        try:
            end_dt = parse_datetime_local(end_time)
        except HTTPException:
            return redirect_with_message(f"/entries/{entry_id}/edit", "Invalid end time.", "error")
        if end_dt <= start_dt:
            return redirect_with_message(
                f"/entries/{entry_id}/edit", "End time must be after start time.", "error"
            )
    else:
        running_other = db.scalar(
            select(TimeEntry.id).where(TimeEntry.end_time.is_(None), TimeEntry.id != entry.id).limit(1)
        )
        if running_other:
            return redirect_with_message(
                f"/entries/{entry_id}/edit",
                "Only one running entry is allowed at a time.",
                "error",
            )
    try:
        validate_project_task(db, project_id, task_id)
    except HTTPException as exc:
        return redirect_with_message(f"/entries/{entry_id}/edit", exc.detail, "error")
    entry.project_id = project_id
    entry.task_id = task_id
    entry.start_time = start_dt
    entry.end_time = end_dt
    entry.notes = notes.strip() or None
    db.commit()
    return redirect_with_message("/entries", "Time entry updated.")


@router.get("/entries/export.csv")
def export_entries_csv(db: Session = Depends(get_db)) -> Response:
    entries = db.scalars(
        select(TimeEntry)
        .options(
            joinedload(TimeEntry.project).joinedload(Project.client),
            joinedload(TimeEntry.task),
        )
        .order_by(TimeEntry.start_time.desc())
    ).all()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["id", "client", "project", "task", "start_time", "end_time", "duration_seconds", "notes"]
    )
    for entry in entries:
        writer.writerow(
            [
                entry.id,
                entry.project.client.name,
                entry.project.name,
                entry.task.name,
                friendly_datetime(entry.start_time),
                friendly_datetime(entry.end_time) if entry.end_time else "",
                entry.duration_seconds or "",
                entry.notes or "",
            ]
        )
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=time_entries.csv"},
    )
