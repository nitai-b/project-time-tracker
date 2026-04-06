# Project Time Tracker

Simple local-first time tracking app built with FastAPI, SQLite, SQLAlchemy, server-rendered Jinja templates, HTMX, and Tailwind CSS.

## Features

- Clients, projects, tasks, and time entries stored as related records
- One active timer at a time
- Pause and resume support for the current timer
- Manual time entry creation and editing
- Project/task validation so a task must belong to the selected project
- Dashboard with current timer, recent entries, and totals for today and this week
- CSV export for time entries
- HTMX-enhanced navigation and form submissions
- Tailwind-based styling with system dark mode support via `prefers-color-scheme`
- Example seed data for `SHP > New Tech Stack Implementation > Zapier Automations Porting to Python`

## File Structure

```text
app/
  __init__.py
  db.py
  main.py
  models.py
  routes.py
  seed.py
static/
  app.js
  styles.css
templates/
  base.html
  clients.html
  dashboard.html
  projects.html
  tasks.html
  time_entries.html
  time_entry_edit.html
data/
  time_tracker.db
requirements.txt
README.md
```

## Setup

1. Create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

## Initialize the Database

The app creates the SQLite database and tables automatically on startup.

Database file:

```text
data/time_tracker.db
```

## Seed Example Data

Run:

```bash
python -m app.seed
```

This safely inserts the example client, project, and task if they do not already exist.

## Run Locally

Start the app with:

```bash
uvicorn app.main:app --reload
```

Then open:

```text
http://127.0.0.1:8000
```

## One-Command Local Setup

You can also run the included script:

```bash
chmod +x run_local.sh
./run_local.sh
```

What it does:

- creates `.venv` if needed
- installs dependencies
- initializes and seeds the database
- starts the FastAPI app
- opens `http://127.0.0.1:8000` in your browser when possible

## Main Relationship Rules

- A `Project` belongs to one `Client` through `client_id`
- A `Task` belongs to one `Project` through `project_id`
- A `TimeEntry` stores `project_id` and `task_id`
- The backend validates that the selected task belongs to the selected project before saving
- The frontend filters visible tasks when a project is selected, but backend validation is still the source of truth

## Notes on Local-First Persistence

- All data is stored locally in SQLite
- No authentication or external services are required
- The UI is server-rendered, so there is no frontend build step
- HTMX and Tailwind are loaded from CDN in the browser, so the UI expects internet access for those frontend assets unless you vendor them locally later

## Turning This into a CLI Later

If you want a CLI version later, the main change is to move more business rules into a shared service layer instead of keeping them mostly in the route handlers.

The first changes I would make:

1. Extract time-entry operations into reusable functions such as `start_timer`, `stop_timer`, `create_manual_entry`, and `validate_project_task`.
2. Keep SQLAlchemy models and session setup unchanged so both the web app and CLI use the same database.
3. Add a small CLI entrypoint using `argparse` or `typer` that calls the shared service functions.
4. Keep formatting concerns separate so the web app renders HTML and the CLI prints tables or plain text.

## Optional Next Improvements

- Add unique constraints for project names per client and task names per project
- Add pagination to time entries
- Add richer reporting views
- Add tags or billable flags to entries
