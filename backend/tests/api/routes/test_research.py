import uuid
from datetime import UTC, datetime


def project(client, headers):
    response = client.post(
        "/api/v1/projects",
        headers=headers,
        json={"name": "量子动力学", "stage": "active"},
    )
    assert response.status_code == 201
    return response.json()


def enroll(client, headers):
    result = client.post(
        "/api/v1/devices",
        headers=headers,
        json={"name": "Lab PC", "platform": "Windows"},
    )
    assert result.status_code == 201
    data = result.json()
    return data["device"], {"Authorization": f"Bearer {data['token']}"}


def test_project_ownership_and_optimistic_updates(
    client, superuser_token_headers, normal_user_token_headers
):
    p = project(client, superuser_token_headers)
    body = {**p, "status_note": "完成基线", "next_step": "扩大样本"}
    response = client.put(
        f"/api/v1/projects/{p['id']}", headers=superuser_token_headers, json=body
    )
    assert response.status_code == 200
    assert response.json()["revision"] == 2
    assert (
        client.put(
            f"/api/v1/projects/{p['id']}", headers=superuser_token_headers, json=body
        ).status_code
        == 409
    )
    assert (
        client.get(
            f"/api/v1/projects/{p['id']}/copies", headers=normal_user_token_headers
        ).status_code
        == 404
    )
    assert (
        client.put(
            f"/api/v1/projects/{p['id']}", headers=normal_user_token_headers, json=body
        ).status_code
        == 404
    )
    assert p["id"] not in [
        p["id"]
        for p in client.get(
            "/api/v1/projects", headers=normal_user_token_headers
        ).json()
    ]


def test_device_scoping_observation_order_and_revocation(
    client, superuser_token_headers, normal_user_token_headers
):
    p = project(client, superuser_token_headers)
    device, headers = enroll(client, superuser_token_headers)
    _, other = enroll(client, normal_user_token_headers)
    registration = {"project_id": p["id"], "local_path": f"C:/research/{uuid.uuid4()}"}
    assert (
        client.post(
            "/api/v1/agent/copies", headers=other, json=registration
        ).status_code
        == 404
    )
    copy = client.post(
        "/api/v1/agent/copies", headers=headers, json=registration
    ).json()
    assert (
        client.post("/api/v1/agent/copies", headers=headers, json=registration).json()[
            "id"
        ]
        == copy["id"]
    )
    other_project = project(client, superuser_token_headers)
    assert (
        client.post(
            "/api/v1/agent/copies",
            headers=headers,
            json={**registration, "project_id": other_project["id"]},
        ).status_code
        == 409
    )
    endpoint = f"/api/v1/agent/copies/{copy['id']}/observations"
    payload = {
        "sequence": 2,
        "observed_at": datetime.now(UTC).isoformat(),
        "dirty": True,
        "changed_files": 1,
        "comparison": "ahead",
        "ahead": 1,
        "behind": 0,
    }
    assert client.post(endpoint, headers=other, json=payload).status_code == 404
    assert client.post(endpoint, headers=headers, json=payload).json()["accepted"]
    assert not client.post(endpoint, headers=headers, json=payload).json()["accepted"]
    assert not client.post(
        endpoint, headers=headers, json={**payload, "sequence": 1, "dirty": False}
    ).json()["accepted"]
    latest = client.get(
        f"/api/v1/projects/{p['id']}/copies", headers=superuser_token_headers
    ).json()[0]
    assert latest["dirty"] and latest["sequence"] == 2
    assert (
        client.post(
            endpoint,
            headers=headers,
            json={
                **payload,
                "sequence": 3,
                "remote_url": "https://token@github.com/me/repo",
            },
        ).status_code
        == 422
    )
    public = client.get("/api/v1/devices", headers=superuser_token_headers).json()
    assert all("token_hash" not in d and "token" not in d for d in public)
    assert client.get("/api/v1/projects", headers=headers).status_code in (401, 403)
    assert (
        client.post(
            f"/api/v1/devices/{device['id']}/revoke", headers=normal_user_token_headers
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/devices/{device['id']}/revoke", headers=superuser_token_headers
        ).status_code
        == 200
    )
    assert (
        client.post("/api/v1/agent/heartbeat", headers=headers, json={}).status_code
        == 401
    )
    assert client.post(endpoint, headers=headers, json=payload).status_code == 401


def test_validation_and_anonymous_access(client, superuser_token_headers):
    assert client.get("/api/v1/projects").status_code == 401
    assert (
        client.post(
            "/api/v1/projects", headers=superuser_token_headers, json={"name": "   "}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/projects",
            headers=superuser_token_headers,
            json={"name": "Test", "stage": "bad"},
        ).status_code
        == 422
    )
