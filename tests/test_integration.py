

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    # The tests run on Windows, so use the ports published by Docker Compose.
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://timetable_user:local_dev_password@localhost:5432/timetable",
    )
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

    from app import cache, db
    from app.main import app

    # Ensure Redis uses the test connection settings.
    cache._client = None

    # Remove leftover test records from an earlier run.
    db.query(
        "DELETE FROM classes WHERE subject LIKE %s",
        ("ITEST-%",),
        fetch=False,
    )
    cache.drop_prefix("tt:")

    with TestClient(app) as test_client:
        yield test_client

    # Clean up test records and cached timetables.
    db.query(
        "DELETE FROM classes WHERE subject LIKE %s",
        ("ITEST-%",),
        fetch=False,
    )
    cache.drop_prefix("tt:")
    cache._client = None


def sample_class(**overrides):
    entry = {
        "day": "mon",
        "start": "15:00",
        "end": "16:00",
        "subject": "ITEST-Python",
        "teacher": "ITEST-Teacher",
        "room": "ITEST-Room",
        "batch": "ITEST-Batch",
    }
    entry.update(overrides)
    return entry


def test_health_checks_postgres_and_redis(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["postgres"] is True
    assert response.json()["redis"] is True


def test_list_classes_returns_seed_data(client):
    response = client.get("/classes")

    assert response.status_code == 200
    body = response.json()
    assert body["count"] >= 17
    assert len(body["classes"]) == body["count"]


def test_list_classes_filters_by_day(client):
    response = client.get("/classes", params={"day": "Monday"})

    assert response.status_code == 200
    assert all(item["day"] == "mon" for item in response.json()["classes"])


def test_list_classes_rejects_invalid_day(client):
    response = client.get("/classes", params={"day": "Sunday"})

    assert response.status_code == 400


def test_create_class_and_read_it_back(client):
    response = client.post("/classes", json=sample_class())

    assert response.status_code == 201
    created = response.json()
    assert created["subject"] == "ITEST-Python"
    assert created["start"] == "15:00"
    assert created["end"] == "16:00"

    listed = client.get("/classes").json()["classes"]
    assert any(item["id"] == created["id"] for item in listed)


def test_check_endpoint_does_not_create_class(client):
    response = client.post("/classes/check", json=sample_class())

    assert response.status_code == 200
    assert response.json()["ok"] is True

    listed = client.get("/classes").json()["classes"]
    assert not any(item["subject"] == "ITEST-Python" for item in listed)


def test_check_endpoint_reports_resource_clashes(client):
    first = client.post("/classes", json=sample_class())
    assert first.status_code == 201

    candidate = sample_class(
        start="15:30",
        end="16:30",
        subject="ITEST-Conflicting",
    )
    response = client.post("/classes/check", json=candidate)

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert {item["field"] for item in body["clashes"]} == {
        "room",
        "teacher",
        "batch",
    }


def test_create_rejects_conflicting_class(client):
    first = client.post("/classes", json=sample_class())
    assert first.status_code == 201

    candidate = sample_class(
        start="15:30",
        end="16:30",
        subject="ITEST-Conflict",
    )
    response = client.post("/classes", json=candidate)

    assert response.status_code == 409


def test_create_rejects_invalid_class(client):
    response = client.post(
        "/classes",
        json=sample_class(start="12:30", end="13:30"),
    )

    assert response.status_code == 400


def test_timetable_uses_redis_cache(client):
    created = client.post("/classes", json=sample_class())
    assert created.status_code == 201

    first = client.get("/timetable/batch/ITEST-Batch")
    assert first.status_code == 200
    assert first.json()["cached"] is False
    assert first.json()["total_classes"] == 1

    second = client.get("/timetable/batch/ITEST-Batch")
    assert second.status_code == 200
    assert second.json()["cached"] is True


def test_timetable_rejects_unknown_kind(client):
    response = client.get("/timetable/subject/Python")

    assert response.status_code == 400


def test_timetable_returns_not_found_for_unknown_value(client):
    response = client.get("/timetable/batch/ITEST-Missing")

    assert response.status_code == 404


def test_free_endpoint_returns_slots(client):
    response = client.get("/free/mon", params={"minutes": 60})

    assert response.status_code == 200
    body = response.json()
    assert body["day"] == "mon"
    assert body["minimum_minutes"] == 60
    assert isinstance(body["free"], list)


def test_free_endpoint_rejects_invalid_day_and_duration(client):
    invalid_day = client.get("/free/sunday")
    invalid_duration = client.get("/free/mon", params={"minutes": 0})

    assert invalid_day.status_code == 400
    assert invalid_duration.status_code == 400


def test_delete_class(client):
    created = client.post("/classes", json=sample_class())
    assert created.status_code == 201
    class_id = created.json()["id"]

    response = client.delete(f"/classes/{class_id}")

    assert response.status_code == 200
    assert response.json()["deleted"]["id"] == class_id


def test_delete_missing_class_returns_404(client):
    response = client.delete("/classes/999999999")

    assert response.status_code == 404
