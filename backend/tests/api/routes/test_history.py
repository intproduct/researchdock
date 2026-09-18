import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest
from sqlmodel import select

from app.research_models import Project, ProjectRevision


def _assert_utc(text: str) -> None:
    """A timestamp must carry an explicit UTC offset, not be tz-naive."""
    assert text.endswith(("Z", "+00:00")), text
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None and parsed.utcoffset() == UTC.utcoffset(
        None
    ), text


def _instant(text: str) -> datetime:
    """Parse an API timestamp; a naive value is the UTC wall clock."""
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def create_project(client, headers, name="量子动力学"):
    response = client.post(
        "/api/v1/projects",
        headers=headers,
        json={"name": name, "stage": "active", "next_step": "搭好基线"},
    )
    assert response.status_code == 201
    return response.json()


def update_project(client, headers, project, **changes):
    body = {**project, **changes}
    return client.put(
        f"/api/v1/projects/{project['id']}", headers=headers, json=body
    )


def history(client, headers, project_id, **params):
    return client.get(
        f"/api/v1/projects/{project_id}/history", headers=headers, params=params
    )


def test_create_records_single_created_snapshot(
    client, db, superuser_token_headers
):
    p = create_project(client, superuser_token_headers)
    assert p["revision"] == 1
    page = history(client, superuser_token_headers, p["id"]).json()
    assert page["next_before_revision"] is None
    assert len(page["items"]) == 1
    item = page["items"][0]
    assert item["revision"] == 1
    assert item["origin"] == "created"
    assert item["snapshot"] == {
        "name": p["name"],
        "description": p["description"],
        "stage": p["stage"],
        "status_note": p["status_note"],
        "next_step": p["next_step"],
    }
    # Same instant as the project's own updated_at (compare instants: the
    # project response is still naive UTC, the history response is explicit).
    assert _instant(item["project_updated_at"]) == _instant(p["updated_at"])
    assert item["recorded_at"]
    # actor_id is the server-side user id, never an email or token
    owner = db.get(Project, uuid.UUID(p["id"]))
    assert item["actor_id"] == str(owner.owner_id)


def test_updates_append_descending_history_and_409_adds_nothing(
    client, superuser_token_headers
):
    p = create_project(client, superuser_token_headers)
    first = update_project(
        client, superuser_token_headers, p, status_note="完成基线"
    )
    assert first.status_code == 200 and first.json()["revision"] == 2
    second = update_project(
        client, superuser_token_headers, first.json(), status_note="扩大样本"
    )
    assert second.status_code == 200 and second.json()["revision"] == 3
    # Replaying the stale request conflicts and must not append history.
    assert (
        update_project(
            client, superuser_token_headers, p, status_note="重复旧请求"
        ).status_code
        == 409
    )
    page = history(client, superuser_token_headers, p["id"]).json()
    assert [item["revision"] for item in page["items"]] == [3, 2, 1]
    assert [item["origin"] for item in page["items"]] == [
        "updated",
        "updated",
        "created",
    ]
    assert page["items"][0]["snapshot"]["status_note"] == "扩大样本"
    assert page["items"][1]["snapshot"]["status_note"] == "完成基线"
    assert _instant(page["items"][0]["project_updated_at"]) == _instant(
        second.json()["updated_at"]
    )


def test_same_content_put_still_appends_revision(client, superuser_token_headers):
    p = create_project(client, superuser_token_headers)
    again = update_project(client, superuser_token_headers, p)
    assert again.status_code == 200 and again.json()["revision"] == 2
    page = history(client, superuser_token_headers, p["id"]).json()
    assert [item["revision"] for item in page["items"]] == [2, 1]
    assert page["items"][0]["snapshot"] == page["items"][1]["snapshot"]


def test_concurrent_same_baseline_only_one_succeeds(
    client, superuser_token_headers
):
    p = create_project(client, superuser_token_headers)

    def attempt(note):
        return update_project(
            client, superuser_token_headers, p, status_note=note
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, ["会话 A", "会话 B"]))
    assert sorted(results) == [200, 409]
    page = history(client, superuser_token_headers, p["id"]).json()
    assert [item["revision"] for item in page["items"]] == [2, 1]


def test_history_insert_failure_rolls_back_project_update(
    client, db, superuser_token_headers, monkeypatch
):
    p = create_project(client, superuser_token_headers)
    from app.api.routes import research

    def broken(*args, **kwargs) -> None:  # noqa: ARG001
        raise RuntimeError("simulated history write failure")

    monkeypatch.setattr(research, "record_revision", broken)
    with pytest.raises(RuntimeError):
        update_project(client, superuser_token_headers, p, status_note="不应落库")
    db.rollback()
    project = db.get(Project, uuid.UUID(p["id"]))
    assert project.revision == 1
    assert project.status_note == p["status_note"]
    # Only the original creation snapshot remains; the failed update added none.
    revisions = db.exec(
        select(ProjectRevision).where(ProjectRevision.project_id == project.id)
    ).all()
    assert [row.revision for row in revisions] == [1]


def test_create_failure_leaves_no_orphan_project(
    client, db, superuser_token_headers, monkeypatch
):
    from app.api.routes import research

    def broken(*args, **kwargs) -> None:  # noqa: ARG001
        raise RuntimeError("simulated history write failure")

    monkeypatch.setattr(research, "record_revision", broken)
    with pytest.raises(RuntimeError):
        create_project(client, superuser_token_headers, name="孤立项目")
    db.rollback()
    assert (
        db.exec(select(Project).where(Project.name == "孤立项目")).first() is None
    )


def test_history_permissions_and_forged_fields(
    client, superuser_token_headers, normal_user_token_headers
):
    p = create_project(client, superuser_token_headers)
    url = f"/api/v1/projects/{p['id']}/history"
    assert client.get(url).status_code == 401
    assert (
        client.get(url, headers=normal_user_token_headers).status_code == 404
    )
    assert (
        client.get(
            f"/api/v1/projects/{uuid.uuid4()}/history",
            headers=superuser_token_headers,
        ).status_code
        == 404
    )
    # Device credentials must not read the user-facing history endpoint.
    device = client.post(
        "/api/v1/devices",
        headers=superuser_token_headers,
        json={"name": "Lab PC", "platform": "Windows"},
    ).json()
    device_headers = {"Authorization": f"Bearer {device['token']}"}
    assert client.get(url, headers=device_headers).status_code in (401, 403)
    # Client-supplied trusted fields are ignored by the server.
    forged = {
        **p,
        "status_note": "伪造字段",
        "actor_id": str(uuid.uuid4()),
        "origin": "migrated_baseline",
        "recorded_at": "1999-01-01T00:00:00Z",
    }
    assert (
        client.put(
            f"/api/v1/projects/{p['id']}",
            headers=superuser_token_headers,
            json=forged,
        ).status_code
        == 200
    )
    item = history(client, superuser_token_headers, p["id"]).json()["items"][0]
    assert item["origin"] == "updated"
    assert item["recorded_at"] > "2026-01-01"
    assert item["actor_id"] != forged["actor_id"]


def test_history_pagination(client, superuser_token_headers):
    p = create_project(client, superuser_token_headers)
    current = p
    for index in range(5):
        current = update_project(
            client,
            superuser_token_headers,
            current,
            status_note=f"第 {index + 2} 版",
        ).json()
    first = history(
        client, superuser_token_headers, p["id"], limit=2
    ).json()
    assert [item["revision"] for item in first["items"]] == [6, 5]
    assert first["next_before_revision"] == 5
    second = history(
        client,
        superuser_token_headers,
        p["id"],
        limit=2,
        before_revision=first["next_before_revision"],
    ).json()
    assert [item["revision"] for item in second["items"]] == [4, 3]
    assert second["next_before_revision"] == 3
    third = history(
        client,
        superuser_token_headers,
        p["id"],
        limit=2,
        before_revision=second["next_before_revision"],
    ).json()
    assert [item["revision"] for item in third["items"]] == [2, 1]
    assert third["next_before_revision"] is None
    # A new revision while paging must not disturb older pages.
    update_project(client, superuser_token_headers, current, status_note="翻页期间新增")
    again = history(
        client, superuser_token_headers, p["id"], limit=2, before_revision=5
    ).json()
    assert [item["revision"] for item in again["items"]] == [4, 3]
    # Invalid pagination parameters are rejected.
    assert (
        history(client, superuser_token_headers, p["id"], limit=0).status_code
        == 422
    )
    assert (
        history(client, superuser_token_headers, p["id"], limit=101).status_code
        == 422
    )
    assert (
        history(
            client, superuser_token_headers, p["id"], before_revision=0
        ).status_code
        == 422
    )


def test_history_timestamps_carry_utc_for_every_origin(
    client, db, superuser_token_headers
):
    """R2: recorded_at / project_updated_at must be explicit UTC over HTTP.

    SQLite hands back naive datetimes for a plain DateTime column, so the API
    boundary has to attach UTC rather than relying on the database driver.
    """
    p = create_project(client, superuser_token_headers)
    updated = update_project(
        client, superuser_token_headers, p, status_note="第二轮"
    )
    assert updated.status_code == 200
    # Simulate the migration backfill: a baseline row written with a naive
    # UTC value, exactly as the SQLite migration produces it.
    baseline = ProjectRevision(
        project_id=uuid.UUID(p["id"]),
        revision=99,
        snapshot={
            "name": "T",
            "description": "",
            "stage": "active",
            "status_note": "迁移前",
            "next_step": "",
        },
        actor_id=None,
        origin="migrated_baseline",
        project_updated_at=datetime(2026, 9, 15, 12, 0, 0),  # naive UTC
    )
    db.add(baseline)
    db.commit()

    page = history(client, superuser_token_headers, p["id"], limit=100).json()
    origins = {item["origin"] for item in page["items"]}
    assert origins == {"created", "updated", "migrated_baseline"}
    for item in page["items"]:
        _assert_utc(item["recorded_at"])
        _assert_utc(item["project_updated_at"])
    # Meaning is preserved: the naive 12:00 value is the UTC instant 12:00,
    # not a re-interpretation in some other offset.
    baseline_item = next(
        item for item in page["items"] if item["origin"] == "migrated_baseline"
    )
    parsed = datetime.fromisoformat(
        baseline_item["project_updated_at"].replace("Z", "+00:00")
    )
    assert parsed.astimezone(UTC).replace(tzinfo=None) == datetime(
        2026, 9, 15, 12, 0, 0
    )
