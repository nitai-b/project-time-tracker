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


def clean_text(value: str | None) -> str:
    return (value or "").strip()


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
        return f"{hours}h {minutes}m {secs}s"
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


def is_entry_running(entry: TimeEntry | None) -> bool:
    return entry is not None and entry.is_running


def pause_entry_timer(entry: TimeEntry, paused_at: datetime | None = None) -> None:
    if not entry.is_running:
        raise HTTPException(status_code=400, detail="Time entry is not running.")
    entry.paused_at = paused_at or datetime.now()


def resume_entry_timer(entry: TimeEntry, resumed_at: datetime | None = None) -> None:
    if not entry.is_paused:
        raise HTTPException(status_code=400, detail="Time entry is not paused.")
    resume_time = resumed_at or datetime.now()
    entry.paused_seconds += max(int((resume_time - entry.paused_at).total_seconds()), 0)
    entry.paused_at = None


def stop_entry_timer(entry: TimeEntry, stopped_at: datetime | None = None) -> None:
    if entry.end_time is not None:
        raise HTTPException(status_code=400, detail="Time entry is already stopped.")
    stop_time = stopped_at or datetime.now()
    if entry.is_paused:
        resume_entry_timer(entry, stop_time)
    entry.end_time = stop_time


def get_form_data(db: Session) -> dict[str, Any]:
    clients = db.scalars(select(Client).order_by(Client.name)).all()
    projects = db.scalars(select(Project).options(joinedload(Project.client)).order_by(Project.name)).all()
    tasks = db.scalars(select(Task).options(joinedload(Task.project)).order_by(Task.name)).all()
    return {"clients": clients, "projects": projects, "tasks": tasks}


def get_client_by_name(db: Session, name: str) -> Client | None:
    return db.scalar(select(Client).where(func.lower(Client.name) == name.lower()))


def get_project_by_name(db: Session, client_id: int, name: str) -> Project | None:
    return db.scalar(
        select(Project).where(Project.client_id == client_id, func.lower(Project.name) == name.lower())
    )


def get_task_by_name(db: Session, project_id: int, name: str) -> Task | None:
    return db.scalar(
        select(Task).where(Task.project_id == project_id, func.lower(Task.name) == name.lower())
    )


def resolve_client_selection(
    db: Session, client_id_value: str | None, new_client_name: str | None, required: bool = False
) -> Client | None:
    client_id = parse_optional_int(client_id_value)
    if client_id:
        client = db.get(Client, client_id)
        if not client:
            raise HTTPException(status_code=404, detail="Selected client was not found.")
        return client

    clean_name = clean_text(new_client_name)
    if clean_name:
        existing = get_client_by_name(db, clean_name)
        if existing:
            return existing
        client = Client(name=clean_name)
        db.add(client)
        db.flush()
        return client

    if required:
        raise HTTPException(status_code=400, detail="Select a client or create a new one.")
    return None


def resolve_project_selection(
    db: Session,
    project_id_value: str | None,
    new_project_name: str | None,
    client: Client | None,
    required: bool = False,
) -> Project | None:
    project_id = parse_optional_int(project_id_value)
    if project_id:
        project = db.get(Project, project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Selected project was not found.")
        if client and project.client_id != client.id:
            raise HTTPException(status_code=400, detail="Selected project does not belong to the selected client.")
        return project

    clean_name = clean_text(new_project_name)
    if clean_name:
        if client is None:
            raise HTTPException(status_code=400, detail="Choose or create a client before creating a project.")
        existing = get_project_by_name(db, client.id, clean_name)
        if existing:
            return existing
        project = Project(client_id=client.id, name=clean_name)
        db.add(project)
        db.flush()
        return project

    if required:
        raise HTTPException(status_code=400, detail="Select a project or create a new one.")
    return None


def resolve_task_selection(
    db: Session,
    task_id_value: str | None,
    new_task_name: str | None,
    project: Project | None,
    required: bool = False,
) -> Task | None:
    task_id = parse_optional_int(task_id_value)
    if task_id:
        task = db.get(Task, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Selected task was not found.")
        if project and task.project_id != project.id:
            raise HTTPException(status_code=400, detail="Selected task does not belong to the selected project.")
        return task

    clean_name = clean_text(new_task_name)
    if clean_name:
        if project is None:
            raise HTTPException(status_code=400, detail="Choose or create a project before creating a task.")
        existing = get_task_by_name(db, project.id, clean_name)
        if existing:
            return existing
        task = Task(project_id=project.id, name=clean_name)
        db.add(task)
        db.flush()
        return task

    if required:
        raise HTTPException(status_code=400, detail="Select a task or create a new one.")
    return None


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
    for entry in entries:
        duration_seconds = entry.duration_seconds
        if duration_seconds is None:
            duration_seconds = entry.elapsed_seconds()
        total += duration_seconds
    return total


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    rendered_at = datetime.now()
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
    today_total = compute_range_totals(
        db,
        datetime.combine(today, time.min),
        datetime.combine(today + timedelta(days=1), time.min),
    )
    week_total = compute_range_totals(
        db,
        datetime.combine(week_start, time.min),
        datetime.combine(week_start + timedelta(days=7), time.min),
    )
    today_total_live = is_entry_running(active_entry) and active_entry.start_time.date() == today
    week_total_live = is_entry_running(active_entry) and active_entry.start_time.date() >= week_start

    context = {
        "request": request,
        "active_entry": active_entry,
        "recent_entries": recent_entries,
        "today_total": today_total,
        "today_total_live": today_total_live,
        "week_total": week_total,
        "week_total_live": week_total_live,
        "rendered_at_iso": rendered_at.isoformat(),
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
    clean_name = clean_text(name)
    if not clean_name:
        return redirect_with_message("/clients", "Client name is required.", "error")
    existing = db.scalar(select(Client).where(func.lower(Client.name) == clean_name.lower()))
    if existing:
        return redirect_with_message("/clients", "Client already exists.", "error")
    db.add(Client(name=clean_name))
    db.commit()
    return redirect_with_message("/clients", "Client created.")


@router.get("/clients/{client_id}/edit", response_class=HTMLResponse)
def edit_client_form(request: Request, client_id: int, db: Session = Depends(get_db)) -> HTMLResponse:
    client = db.get(Client, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found.")
    return request.app.state.templates.TemplateResponse(
        "client_edit.html", {"request": request, "client": client}
    )


@router.post("/clients/{client_id}/edit")
def update_client(
    client_id: int, name: str = Form(...), db: Session = Depends(get_db)
) -> RedirectResponse:
    client = db.get(Client, client_id)
    if not client:
        return redirect_with_message("/clients", "Client not found.", "error")
    clean_name = clean_text(name)
    if not clean_name:
        return redirect_with_message(f"/clients/{client_id}/edit", "Client name is required.", "error")
    existing = db.scalar(
        select(Client).where(func.lower(Client.name) == clean_name.lower(), Client.id != client.id)
    )
    if existing:
        return redirect_with_message(f"/clients/{client_id}/edit", "Client already exists.", "error")
    client.name = clean_name
    db.commit()
    return redirect_with_message("/clients", "Client updated.")


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
    client_id: str = Form(""),
    new_client_name: str = Form(""),
    name: str = Form(...),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    clean_name = clean_text(name)
    try:
        client = resolve_client_selection(db, client_id, new_client_name, required=True)
    except HTTPException as exc:
        return redirect_with_message("/projects", exc.detail, "error")
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


@router.get("/projects/{project_id}/edit", response_class=HTMLResponse)
def edit_project_form(request: Request, project_id: int, db: Session = Depends(get_db)) -> HTMLResponse:
    project = db.scalar(
        select(Project).options(joinedload(Project.client)).where(Project.id == project_id)
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    return request.app.state.templates.TemplateResponse(
        "project_edit.html",
        {
            "request": request,
            "project": project,
            "clients": db.scalars(select(Client).order_by(Client.name)).all(),
        },
    )


@router.post("/projects/{project_id}/edit")
def update_project(
    project_id: int,
    client_id: str = Form(""),
    new_client_name: str = Form(""),
    name: str = Form(...),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    project = db.get(Project, project_id)
    if not project:
        return redirect_with_message("/projects", "Project not found.", "error")
    clean_name = clean_text(name)
    if not clean_name:
        return redirect_with_message(f"/projects/{project_id}/edit", "Project name is required.", "error")
    try:
        client = resolve_client_selection(db, client_id, new_client_name, required=True)
    except HTTPException as exc:
        return redirect_with_message(f"/projects/{project_id}/edit", exc.detail, "error")
    existing = db.scalar(
        select(Project).where(
            Project.client_id == client.id,
            func.lower(Project.name) == clean_name.lower(),
            Project.id != project.id,
        )
    )
    if existing:
        return redirect_with_message(
            f"/projects/{project_id}/edit", "Project already exists for this client.", "error"
        )
    project.client_id = client.id
    project.name = clean_name
    db.commit()
    return redirect_with_message("/projects", "Project updated.")


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
        {
            "request": request,
            "tasks": tasks,
            "projects": db.scalars(select(Project).options(joinedload(Project.client)).order_by(Project.name)).all(),
            "clients": db.scalars(select(Client).order_by(Client.name)).all(),
        },
    )


@router.post("/tasks")
def create_task(
    project_id: str = Form(""),
    new_project_name: str = Form(""),
    client_id: str = Form(""),
    new_client_name: str = Form(""),
    name: str = Form(...),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    clean_name = clean_text(name)
    try:
        client = resolve_client_selection(db, client_id, new_client_name, required=bool(clean_text(new_project_name)))
        project = resolve_project_selection(db, project_id, new_project_name, client, required=True)
    except HTTPException as exc:
        return redirect_with_message("/tasks", exc.detail, "error")
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


@router.get("/tasks/{task_id}/edit", response_class=HTMLResponse)
def edit_task_form(request: Request, task_id: int, db: Session = Depends(get_db)) -> HTMLResponse:
    task = db.scalar(
        select(Task)
        .options(joinedload(Task.project).joinedload(Project.client))
        .where(Task.id == task_id)
    )
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")
    return request.app.state.templates.TemplateResponse(
        "task_edit.html",
        {
            "request": request,
            "task": task,
            **get_form_data(db),
        },
    )


@router.post("/tasks/{task_id}/edit")
def update_task(
    task_id: int,
    project_id: str = Form(""),
    new_project_name: str = Form(""),
    client_id: str = Form(""),
    new_client_name: str = Form(""),
    name: str = Form(...),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    task = db.get(Task, task_id)
    if not task:
        return redirect_with_message("/tasks", "Task not found.", "error")
    clean_name = clean_text(name)
    if not clean_name:
        return redirect_with_message(f"/tasks/{task_id}/edit", "Task name is required.", "error")
    try:
        client = resolve_client_selection(db, client_id, new_client_name, required=bool(clean_text(new_project_name)))
        project = resolve_project_selection(db, project_id, new_project_name, client, required=True)
    except HTTPException as exc:
        return redirect_with_message(f"/tasks/{task_id}/edit", exc.detail, "error")
    existing = db.scalar(
        select(Task).where(
            Task.project_id == project.id,
            func.lower(Task.name) == clean_name.lower(),
            Task.id != task.id,
        )
    )
    if existing:
        return redirect_with_message(
            f"/tasks/{task_id}/edit", "Task already exists for this project.", "error"
        )
    task.project_id = project.id
    task.name = clean_name
    db.commit()
    return redirect_with_message("/tasks", "Task updated.")


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
    rendered_at = datetime.now()
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
        "rendered_at_iso": rendered_at.isoformat(),
        "form_defaults": {
            "start_time": datetime_input_value(datetime.now()),
            "end_time": datetime_input_value(datetime.now()),
        },
        **get_form_data(db),
    }
    return request.app.state.templates.TemplateResponse("time_entries.html", context)


@router.post("/entries/manual")
def create_manual_entry(
    client_id: str = Form(""),
    new_client_name: str = Form(""),
    project_id: str = Form(""),
    new_project_name: str = Form(""),
    task_id: str = Form(""),
    new_task_name: str = Form(""),
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
        client = resolve_client_selection(db, client_id, new_client_name, required=bool(clean_text(new_project_name)))
        project = resolve_project_selection(db, project_id, new_project_name, client, required=True)
        task = resolve_task_selection(db, task_id, new_task_name, project, required=True)
    except HTTPException as exc:
        return redirect_with_message("/entries", exc.detail, "error")
    db.add(
        TimeEntry(
            project_id=project.id,
            task_id=task.id,
            start_time=start_dt,
            end_time=end_dt,
            notes=notes.strip() or None,
        )
    )
    db.commit()
    return redirect_with_message("/entries", "Time entry created.")


@router.post("/entries/start")
def start_entry(
    client_id: str = Form(""),
    new_client_name: str = Form(""),
    project_id: str = Form(""),
    new_project_name: str = Form(""),
    task_id: str = Form(""),
    new_task_name: str = Form(""),
    start_time: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    if get_active_entry(db):
        return redirect_with_message("/", "Finish the current timer before starting another one.", "error")
    try:
        client = resolve_client_selection(db, client_id, new_client_name, required=bool(clean_text(new_project_name)))
        project = resolve_project_selection(db, project_id, new_project_name, client, required=True)
        task = resolve_task_selection(db, task_id, new_task_name, project, required=True)
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
            project_id=project.id,
            task_id=task.id,
            start_time=start_dt,
            end_time=None,
            paused_at=None,
            paused_seconds=0,
            notes=notes.strip() or None,
        )
    )
    db.commit()
    return redirect_with_message("/", "Timer started.")


@router.post("/entries/{entry_id}/pause")
def pause_entry(
    entry_id: int, next_path: str = Form("/"), db: Session = Depends(get_db)
) -> RedirectResponse:
    entry = db.get(TimeEntry, entry_id)
    if not entry:
        return redirect_with_message(next_path or "/", "Time entry not found.", "error")
    try:
        pause_entry_timer(entry)
    except HTTPException as exc:
        return redirect_with_message(next_path or "/", exc.detail, "error")
    db.commit()
    return redirect_with_message(next_path or "/", "Timer paused.")


@router.post("/entries/{entry_id}/resume")
def resume_entry(
    entry_id: int, next_path: str = Form("/"), db: Session = Depends(get_db)
) -> RedirectResponse:
    entry = db.get(TimeEntry, entry_id)
    if not entry:
        return redirect_with_message(next_path or "/", "Time entry not found.", "error")
    try:
        resume_entry_timer(entry)
    except HTTPException as exc:
        return redirect_with_message(next_path or "/", exc.detail, "error")
    db.commit()
    return redirect_with_message(next_path or "/", "Timer resumed.")


@router.post("/entries/{entry_id}/stop")
def stop_entry(
    entry_id: int, next_path: str = Form("/"), db: Session = Depends(get_db)
) -> RedirectResponse:
    entry = db.get(TimeEntry, entry_id)
    if not entry:
        return redirect_with_message(next_path or "/", "Time entry not found.", "error")
    try:
        stop_entry_timer(entry)
    except HTTPException as exc:
        return redirect_with_message(next_path or "/", exc.detail, "error")
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
    if end_dt is not None:
        entry.paused_at = None
        entry.paused_seconds = 0
    elif entry.paused_at is not None and entry.paused_at <= start_dt:
        return redirect_with_message(
            f"/entries/{entry_id}/edit",
            "Paused time must be after the start time.",
            "error",
        )
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
