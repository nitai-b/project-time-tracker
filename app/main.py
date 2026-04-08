from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.routes import (
    datetime_input_value,
    format_duration,
    friendly_datetime,
    router,
)
from app.seed import seed_example_data


BASE_DIR = Path(__file__).resolve().parent.parent

app = FastAPI(title="Project Time Tracker")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.globals["format_duration"] = format_duration
templates.env.globals["friendly_datetime"] = friendly_datetime
templates.env.globals["datetime_input_value"] = datetime_input_value
app.state.templates = templates

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.include_router(router)


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/seed")
def seed_data() -> dict[str, str]:
    seed_example_data()
    return {"status": "seeded"}
