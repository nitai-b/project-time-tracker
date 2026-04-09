from datetime import datetime

from app.models import Task, TimeEntry


def test_soft_deleting_task_cascades_to_entries_and_hides_them_by_default(
    client, session_factory, project_task_ids, frozen_time
):
    frozen_time.current = datetime(2026, 4, 8, 9, 0, 0)
    start_response = client.post(
        "/entries/start",
        data={
            "project_id": str(project_task_ids["project_id"]),
            "task_id": str(project_task_ids["task_id"]),
            "start_time": "2026-04-08T09:00:00",
        },
        follow_redirects=False,
    )
    assert start_response.status_code == 303

    frozen_time.current = datetime(2026, 4, 8, 9, 20, 0)
    delete_response = client.post(
        f"/tasks/{project_task_ids['task_id']}/delete",
        data={"next_path": "/tasks?status=all"},
        follow_redirects=False,
    )
    assert delete_response.status_code == 303

    session = session_factory()
    try:
        task = session.get(Task, project_task_ids["task_id"])
        entry = session.query(TimeEntry).one()
        assert task.is_deleted
        assert entry.is_deleted
        assert entry.end_time == datetime(2026, 4, 8, 9, 20, 0)
    finally:
        session.close()

    active_entries = client.get("/entries")
    assert active_entries.status_code == 200
    assert "Build timer" not in active_entries.text

    all_tasks = client.get("/tasks", params={"status": "all"})
    assert all_tasks.status_code == 200
    assert "Restore" in all_tasks.text
    assert "Deleted" in all_tasks.text


def test_restoring_deleted_entry_makes_it_visible_again(client, session_factory, project_task_ids, frozen_time):
    frozen_time.current = datetime(2026, 4, 8, 9, 0, 0)
    start_response = client.post(
        "/entries/start",
        data={
            "project_id": str(project_task_ids["project_id"]),
            "task_id": str(project_task_ids["task_id"]),
            "start_time": "2026-04-08T09:00:00",
        },
        follow_redirects=False,
    )
    assert start_response.status_code == 303

    session = session_factory()
    try:
        entry = session.query(TimeEntry).one()
        entry_id = entry.id
    finally:
        session.close()

    frozen_time.current = datetime(2026, 4, 8, 9, 5, 0)
    delete_response = client.post(
        f"/entries/{entry_id}/delete",
        data={"next_path": "/entries?status=all"},
        follow_redirects=False,
    )
    assert delete_response.status_code == 303

    deleted_entries = client.get("/entries", params={"status": "deleted"})
    assert deleted_entries.status_code == 200
    assert "Restore" in deleted_entries.text
    assert "Deleted" in deleted_entries.text

    restore_response = client.post(
        f"/entries/{entry_id}/restore",
        data={"next_path": "/entries?status=active"},
        follow_redirects=False,
    )
    assert restore_response.status_code == 303

    restored_entries = client.get("/entries")
    assert restored_entries.status_code == 200
    assert "Build timer" in restored_entries.text
