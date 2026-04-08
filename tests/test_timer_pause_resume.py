from datetime import datetime

from app.models import TimeEntry


def test_elapsed_seconds_excludes_multiple_pause_windows():
    entry = TimeEntry(
        project_id=1,
        task_id=1,
        start_time=datetime(2026, 4, 8, 9, 0, 0),
        end_time=datetime(2026, 4, 8, 10, 0, 0),
        paused_seconds=(15 * 60) + (5 * 60),
    )

    assert entry.elapsed_seconds() == 40 * 60
    assert entry.duration_seconds == 40 * 60


def test_timer_routes_accumulate_only_active_time(client, session_factory, project_task_ids, frozen_time):
    frozen_time.current = datetime(2026, 4, 8, 9, 0, 0)
    response = client.post(
        "/entries/start",
        data={
            "project_id": str(project_task_ids["project_id"]),
            "task_id": str(project_task_ids["task_id"]),
            "start_time": "2026-04-08T09:00:00",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    session = session_factory()
    try:
        entry = session.query(TimeEntry).one()
        entry_id = entry.id
        assert entry.is_running

        frozen_time.current = datetime(2026, 4, 8, 9, 10, 0)
        response = client.post(f"/entries/{entry_id}/pause", follow_redirects=False)
        assert response.status_code == 303
        session.refresh(entry)
        assert entry.is_paused
        assert entry.paused_at == datetime(2026, 4, 8, 9, 10, 0)

        frozen_time.current = datetime(2026, 4, 8, 9, 25, 0)
        response = client.post(f"/entries/{entry_id}/resume", follow_redirects=False)
        assert response.status_code == 303
        session.refresh(entry)
        assert entry.is_running
        assert entry.paused_seconds == 15 * 60

        frozen_time.current = datetime(2026, 4, 8, 9, 40, 0)
        response = client.post(f"/entries/{entry_id}/pause", follow_redirects=False)
        assert response.status_code == 303
        session.refresh(entry)
        assert entry.is_paused
        assert entry.paused_at == datetime(2026, 4, 8, 9, 40, 0)

        frozen_time.current = datetime(2026, 4, 8, 9, 45, 0)
        response = client.post(f"/entries/{entry_id}/resume", follow_redirects=False)
        assert response.status_code == 303
        session.refresh(entry)
        assert entry.is_running
        assert entry.paused_seconds == 20 * 60

        frozen_time.current = datetime(2026, 4, 8, 10, 0, 0)
        response = client.post(f"/entries/{entry_id}/stop", follow_redirects=False)
        assert response.status_code == 303
        session.refresh(entry)
        assert entry.end_time == datetime(2026, 4, 8, 10, 0, 0)
        assert entry.duration_seconds == 40 * 60
    finally:
        session.close()


def test_stopping_while_paused_keeps_pause_time_out_of_duration(
    client, session_factory, project_task_ids, frozen_time
):
    frozen_time.current = datetime(2026, 4, 8, 9, 0, 0)
    response = client.post(
        "/entries/start",
        data={
            "project_id": str(project_task_ids["project_id"]),
            "task_id": str(project_task_ids["task_id"]),
            "start_time": "2026-04-08T09:00:00",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    session = session_factory()
    try:
        entry = session.query(TimeEntry).one()
        entry_id = entry.id

        frozen_time.current = datetime(2026, 4, 8, 9, 15, 0)
        response = client.post(f"/entries/{entry_id}/pause", follow_redirects=False)
        assert response.status_code == 303

        frozen_time.current = datetime(2026, 4, 8, 9, 30, 0)
        response = client.post(f"/entries/{entry_id}/stop", follow_redirects=False)
        assert response.status_code == 303

        session.refresh(entry)
        assert entry.end_time == datetime(2026, 4, 8, 9, 30, 0)
        assert entry.paused_seconds == 15 * 60
        assert entry.duration_seconds == 15 * 60
    finally:
        session.close()
