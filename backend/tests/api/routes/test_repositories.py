"""T03 Repository identity, explicit copy binding, and legacy compatibility.

Covers the user-facing repository CRUD and binding contract, the agent
registration/retry rules, and the ownership/device-role boundaries. Concurrency
(A05) is exercised via the TestClient against the live session-scoped database;
on PostgreSQL (TEST_DATABASE_URL) the same tests prove the conditional UPDATE
holds on a real concurrent engine. Migration upgrade paths (A10) and the
end-to-end UI (A11/A13) live in their own suites.
"""
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime


def project(client, headers, name="论文A"):
    response = client.post(
        "/api/v1/projects", headers=headers, json={"name": name, "stage": "active"}
    )
    assert response.status_code == 201
    return response.json()


def enroll(client, headers, name="Lab PC"):
    result = client.post(
        "/api/v1/devices", headers=headers, json={"name": name, "platform": "Windows"}
    )
    assert result.status_code == 201
    data = result.json()
    return data["device"], {"Authorization": f"Bearer {data['token']}"}


def make_repository(client, headers, project_id, name="分析代码"):
    response = client.post(
        f"/api/v1/projects/{project_id}/repositories",
        headers=headers,
        json={"name": name},
    )
    assert response.status_code == 201
    return response.json()


def register(client, device_headers, project_id, path, repository_id=None):
    body = {"project_id": project_id, "local_path": path}
    if repository_id is not None:
        body["repository_id"] = repository_id
    return client.post("/api/v1/agent/copies", headers=device_headers, json=body)


# --- A03: create / rename / validation / stable UUID / revision conflict ---


def test_repository_create_rename_and_validation(client, superuser_token_headers):
    h = superuser_token_headers
    p = project(client, h)
    repo = make_repository(client, h, p["id"], "  分析代码  ")
    assert repo["name"] == "分析代码"  # trimmed
    assert repo["revision"] == 1
    assert repo["project_id"] == p["id"]
    for field in ("id", "created_at", "updated_at"):
        assert repo[field]

    # Duplicate names in the same project are allowed and never merge.
    same_name = make_repository(client, h, p["id"], "分析代码")
    assert same_name["id"] != repo["id"]

    # Validation: blank and overlong names and unknown fields are rejected.
    assert (
        client.post(
            f"/api/v1/projects/{p['id']}/repositories", headers=h, json={"name": "  "}
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/v1/projects/{p['id']}/repositories", headers=h, json={"name": "x" * 121}
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/v1/projects/{p['id']}/repositories",
            headers=h,
            json={"name": "ok", "project_id": p["id"]},
        ).status_code
        == 422
    )

    # Rename keeps the UUID and bumps revision; a stale expectation conflicts.
    renamed = client.put(
        f"/api/v1/repositories/{repo['id']}",
        headers=h,
        json={"name": "分析代码 v2", "revision": 1},
    )
    assert renamed.status_code == 200
    assert renamed.json()["id"] == repo["id"]
    assert renamed.json()["revision"] == 2
    assert (
        client.put(
            f"/api/v1/repositories/{repo['id']}",
            headers=h,
            json={"name": "过期改名", "revision": 1},
        ).status_code
        == 409
    )
    # A legal same-name submit is still one successful update.
    again = client.put(
        f"/api/v1/repositories/{repo['id']}",
        headers=h,
        json={"name": "分析代码 v2", "revision": 2},
    )
    assert again.status_code == 200 and again.json()["revision"] == 3

    # Renaming must not touch Project.revision or append a T01 snapshot.
    proj = client.get("/api/v1/projects", headers=h).json()
    assert next(x for x in proj if x["id"] == p["id"])["revision"] == 1
    history = client.get(f"/api/v1/projects/{p['id']}/history", headers=h).json()
    assert [i["revision"] for i in history["items"]] == [1]


def test_repository_listing_stable_order_and_empty(client, superuser_token_headers):
    h = superuser_token_headers
    p = project(client, h)
    assert client.get(f"/api/v1/projects/{p['id']}/repositories", headers=h).json() == []
    a = make_repository(client, h, p["id"], "甲")
    b = make_repository(client, h, p["id"], "乙")
    listed = client.get(f"/api/v1/projects/{p['id']}/repositories", headers=h).json()
    assert {r["id"] for r in listed} == {a["id"], b["id"]}
    # created_at is non-decreasing along the returned (created_at, id) order.
    created = [r["created_at"] for r in listed]
    assert created == sorted(created)


# --- A04: bind / rebind / unbind / same-value retry ---


def test_copy_binding_lifecycle_and_binding_revision(client, superuser_token_headers):
    h = superuser_token_headers
    p = project(client, h)
    repo_a = make_repository(client, h, p["id"], "分析")
    repo_b = make_repository(client, h, p["id"], "排版")
    _, dh = enroll(client, h)

    path = f"C:/research/{uuid.uuid4()}"
    copy = register(client, dh, p["id"], path).json()
    assert copy["repository_id"] is None and copy["binding_revision"] == 0

    # Associate to repo A.
    bound = client.put(
        f"/api/v1/copies/{copy['id']}/repository",
        headers=h,
        json={"repository_id": repo_a["id"], "binding_revision": 0},
    )
    assert bound.status_code == 200
    assert bound.json()["repository_id"] == repo_a["id"]
    assert bound.json()["binding_revision"] == 1

    # Same target with the *current* expectation is a no-op (no version bump).
    noop = client.put(
        f"/api/v1/copies/{copy['id']}/repository",
        headers=h,
        json={"repository_id": repo_a["id"], "binding_revision": 1},
    )
    assert noop.status_code == 200 and noop.json()["binding_revision"] == 1

    # Stale expectation conflicts even when the target already matches.
    assert (
        client.put(
            f"/api/v1/copies/{copy['id']}/repository",
            headers=h,
            json={"repository_id": repo_a["id"], "binding_revision": 0},
        ).status_code
        == 409
    )

    # Rebind A -> B with the valid expectation.
    rebound = client.put(
        f"/api/v1/copies/{copy['id']}/repository",
        headers=h,
        json={"repository_id": repo_b["id"], "binding_revision": 1},
    )
    assert rebound.status_code == 200
    assert rebound.json()["repository_id"] == repo_b["id"]
    assert rebound.json()["binding_revision"] == 2

    # Unbind to uncategorized.
    unbound = client.put(
        f"/api/v1/copies/{copy['id']}/repository",
        headers=h,
        json={"repository_id": None, "binding_revision": 2},
    )
    assert unbound.status_code == 200
    assert unbound.json()["repository_id"] is None
    assert unbound.json()["binding_revision"] == 3

    # ID and sequence are untouched by every rebind above.
    assert unbound.json()["id"] == copy["id"]
    assert unbound.json()["sequence"] == copy["sequence"] == 0


def test_binding_rejects_cross_project_and_bad_values(
    client, superuser_token_headers
):
    h = superuser_token_headers
    p1, p2 = project(client, h, "项目一"), project(client, h, "项目二")
    other_repo = make_repository(client, h, p2["id"], "别项目仓库")
    _, dh = enroll(client, h)
    copy = register(client, dh, p1["id"], f"C:/research/{uuid.uuid4()}").json()

    # Cross-project repository bind -> 422, nothing written.
    assert (
        client.put(
            f"/api/v1/copies/{copy['id']}/repository",
            headers=h,
            json={"repository_id": other_repo["id"], "binding_revision": 0},
        ).status_code
        == 422
    )
    # Negative binding_revision -> 422.
    assert (
        client.put(
            f"/api/v1/copies/{copy['id']}/repository",
            headers=h,
            json={"repository_id": None, "binding_revision": -1},
        ).status_code
        == 422
    )
    # Unknown field -> 422.
    assert (
        client.put(
            f"/api/v1/copies/{copy['id']}/repository",
            headers=h,
            json={"repository_id": None, "binding_revision": 0, "project_id": p2["id"]},
        ).status_code
        == 422
    )
    # A nonexistent repository id and another account's repository both -> 404,
    # so the caller cannot distinguish existence from the status code.
    assert (
        client.put(
            f"/api/v1/copies/{copy['id']}/repository",
            headers=h,
            json={"repository_id": str(uuid.uuid4()), "binding_revision": 0},
        ).status_code
        == 404
    )
    # State unchanged after the rejected attempts.
    current = client.get(f"/api/v1/projects/{p1['id']}/copies", headers=h).json()[0]
    assert current["repository_id"] is None and current["binding_revision"] == 0


def test_binding_target_ownership_status_layering(
    client, superuser_token_headers, normal_user_token_headers
):
    """R3 regression: nonexistent and other-account repos are both 404; only the
    caller's own other project is 422; the copy's own project succeeds."""
    h, oh = superuser_token_headers, normal_user_token_headers
    p1, p2 = project(client, h, "项目一"), project(client, h, "项目二")
    own_other = make_repository(client, h, p2["id"])  # same account, other project
    own_here = make_repository(client, h, p1["id"])  # same account, same project
    _, dh = enroll(client, h)
    copy = register(client, dh, p1["id"], f"C:/research/{uuid.uuid4()}").json()
    url = f"/api/v1/copies/{copy['id']}/repository"

    # Another account's repository and a nonexistent id must return the SAME
    # status AND body, so the response never reveals whether the UUID exists.
    other_p = project(client, oh, "别人项目")
    other_repo = make_repository(client, oh, other_p["id"])
    resp_other = client.put(
        url, headers=h, json={"repository_id": other_repo["id"], "binding_revision": 0}
    )
    resp_missing = client.put(
        url, headers=h, json={"repository_id": str(uuid.uuid4()), "binding_revision": 0}
    )
    assert resp_other.status_code == 404 and resp_missing.status_code == 404
    assert resp_other.json() == resp_missing.json()  # identical error body
    # Own account but different project -> 422 (a distinct, intentional signal).
    assert (
        client.put(url, headers=h, json={"repository_id": own_other["id"], "binding_revision": 0}).status_code
        == 422
    )
    # Rejections left the copy untouched.
    untouched = client.get(f"/api/v1/projects/{p1['id']}/copies", headers=h).json()[0]
    assert untouched["repository_id"] is None and untouched["binding_revision"] == 0
    # Own account, same project -> 200.
    ok = client.put(url, headers=h, json={"repository_id": own_here["id"], "binding_revision": 0})
    assert ok.status_code == 200 and ok.json()["repository_id"] == own_here["id"]
    # Only the successful bind advanced the version.
    assert ok.json()["binding_revision"] == 1

    # Same layering (status AND body) for the device registration entry point.
    p_agent_other = project(client, h, "项目三")
    agent_foreign = make_repository(client, h, p_agent_other["id"])
    r_missing = register(client, dh, p1["id"], f"C:/research/{uuid.uuid4()}", repository_id=str(uuid.uuid4()))
    r_other = register(client, dh, p1["id"], f"C:/research/{uuid.uuid4()}", repository_id=other_repo["id"])
    r_own_other = register(client, dh, p1["id"], f"C:/research/{uuid.uuid4()}", repository_id=agent_foreign["id"])
    assert r_missing.status_code == 404 and r_other.status_code == 404
    assert r_missing.json() == r_other.json()  # no existence leak via body
    assert r_own_other.status_code == 422


# --- A06: cross-account isolation and device role boundaries ---


def test_repository_cross_account_and_device_role(
    client, superuser_token_headers, normal_user_token_headers
):
    h, oh = superuser_token_headers, normal_user_token_headers
    p = project(client, h)
    repo = make_repository(client, h, p["id"])
    _, dh = enroll(client, h)
    copy = register(client, dh, p["id"], f"C:/research/{uuid.uuid4()}").json()

    # Another account cannot see or touch the project/repository/copy.
    assert (
        client.get(f"/api/v1/projects/{p['id']}/repositories", headers=oh).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/projects/{p['id']}/repositories", headers=oh, json={"name": "x"}
        ).status_code
        == 404
    )
    assert (
        client.put(
            f"/api/v1/repositories/{repo['id']}", headers=oh, json={"name": "x", "revision": 1}
        ).status_code
        == 404
    )
    assert (
        client.put(
            f"/api/v1/copies/{copy['id']}/repository",
            headers=oh,
            json={"repository_id": repo["id"], "binding_revision": 0},
        ).status_code
        == 404
    )

    # A device cannot create/rename repositories or change bindings.
    assert (
        client.post(
            f"/api/v1/projects/{p['id']}/repositories", headers=dh, json={"name": "x"}
        ).status_code
        in (401, 403)
    )
    assert (
        client.put(
            f"/api/v1/repositories/{repo['id']}", headers=dh, json={"name": "x", "revision": 1}
        ).status_code
        in (401, 403)
    )
    assert (
        client.put(
            f"/api/v1/copies/{copy['id']}/repository",
            headers=dh,
            json={"repository_id": repo["id"], "binding_revision": 0},
        ).status_code
        in (401, 403)
    )

    # A device CAN read its owner's project repository list (read-only).
    listed = client.get(
        f"/api/v1/agent/projects/{p['id']}/repositories", headers=dh
    )
    assert listed.status_code == 200
    assert [r["id"] for r in listed.json()] == [repo["id"]]
    # ...but not another account's project list.
    assert (
        client.get(f"/api/v1/agent/projects/{p['id']}/repositories", headers=oh).status_code
        in (401, 403)
    )

    # A revoked device is rejected from the read-only listing too.
    client.post(f"/api/v1/devices/{copy['device_id']}/revoke", headers=h)
    assert (
        client.get(f"/api/v1/agent/projects/{p['id']}/repositories", headers=dh).status_code
        == 401
    )


# --- A07/A08: registration retry, idempotency, legacy (no repository_id) ---


def test_agent_registration_retry_and_legacy_compatibility(
    client, superuser_token_headers
):
    h = superuser_token_headers
    p = project(client, h)
    repo = make_repository(client, h, p["id"])
    _, dh = enroll(client, h)
    path = f"C:/research/{uuid.uuid4()}"

    # Legacy registration (no repository_id) creates an uncategorized copy.
    legacy = register(client, dh, p["id"], path)
    assert legacy.status_code == 200
    legacy_copy = legacy.json()
    assert legacy_copy["repository_id"] is None and legacy_copy["binding_revision"] == 0

    # Owner binds it to a repository via the web.
    client.put(
        f"/api/v1/copies/{legacy_copy['id']}/repository",
        headers=h,
        json={"repository_id": repo["id"], "binding_revision": 0},
    )

    # A legacy re-registration (no repository_id) must NOT clear the binding.
    again = register(client, dh, p["id"], path)
    assert again.status_code == 200
    assert again.json()["repository_id"] == repo["id"]
    assert again.json()["binding_revision"] == 1

    # Idempotent retry with the SAME repository_id returns the existing binding.
    same = register(client, dh, p["id"], path, repository_id=repo["id"])
    assert same.status_code == 200
    assert same.json()["binding_revision"] == 1

    # A DIFFERENT repository_id on a registered path conflicts (no reclassify).
    other = make_repository(client, h, p["id"], "另一个")
    conflict = register(client, dh, p["id"], path, repository_id=other["id"])
    assert conflict.status_code == 409

    # The binding was not changed by the conflicting registration attempt.
    current = client.get(f"/api/v1/projects/{p['id']}/copies", headers=h).json()[0]
    assert current["repository_id"] == repo["id"]

    # Registering with a repository that belongs to another project -> 422,
    # and must not create an orphan copy.
    p2 = project(client, h, "项目二")
    foreign = make_repository(client, h, p2["id"])
    rejected = register(
        client, dh, p["id"], f"C:/research/{uuid.uuid4()}", repository_id=foreign["id"]
    )
    assert rejected.status_code == 422

    # A nonexistent repository id is 404 (not 422): no existence signal.
    missing = register(
        client, dh, p["id"], f"C:/research/{uuid.uuid4()}", repository_id=str(uuid.uuid4())
    )
    assert missing.status_code == 404

    # Registering with an explicit repository at creation starts at binding 1.
    bound_at_creation = register(
        client, dh, p["id"], f"C:/research/{uuid.uuid4()}", repository_id=repo["id"]
    )
    assert bound_at_creation.status_code == 200
    assert bound_at_creation.json()["binding_revision"] == 1


# --- A05: two independent connections rebinding from one baseline ---


def test_concurrent_rebind_same_baseline_only_one_succeeds(
    client, superuser_token_headers
):
    h = superuser_token_headers
    p = project(client, h)
    repo_a = make_repository(client, h, p["id"], "甲")
    repo_b = make_repository(client, h, p["id"], "乙")
    _, dh = enroll(client, h)
    copy = register(client, dh, p["id"], f"C:/research/{uuid.uuid4()}").json()

    def attempt(repository_id):
        return client.put(
            f"/api/v1/copies/{copy['id']}/repository",
            headers=h,
            json={"repository_id": repository_id, "binding_revision": 0},
        ).status_code

    # Two sessions read binding_revision=0, then submit different targets.
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, [repo_a["id"], repo_b["id"]]))
    assert sorted(results) == [200, 409]

    # Exactly one binding won; the version advanced exactly once.
    current = client.get(f"/api/v1/projects/{p['id']}/copies", headers=h).json()[0]
    assert current["binding_revision"] == 1
    assert current["repository_id"] in (repo_a["id"], repo_b["id"])


def test_concurrent_registration_no_duplicate_copy(client, superuser_token_headers):
    h = superuser_token_headers
    p = project(client, h)
    _, dh = enroll(client, h)
    path = f"C:/research/{uuid.uuid4()}"

    def attempt(_):
        return register(client, dh, p["id"], path).status_code

    # Concurrent first registrations of the same (device, path) collapse to one
    # row via the unique constraint; retries read the same id back.
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(attempt, range(4)))
    assert all(code == 200 for code in results)
    copies = client.get(f"/api/v1/projects/{p['id']}/copies", headers=h).json()
    assert len(copies) == 1


def test_observation_does_not_overwrite_binding(client, superuser_token_headers):
    h = superuser_token_headers
    p = project(client, h)
    repo = make_repository(client, h, p["id"])
    _, dh = enroll(client, h)
    copy = register(
        client, dh, p["id"], f"C:/research/{uuid.uuid4()}", repository_id=repo["id"]
    ).json()

    payload = {
        "sequence": 1,
        "observed_at": datetime.now(UTC).isoformat(),
        "dirty": True,
        "changed_files": 2,
        "comparison": "ahead",
        "ahead": 1,
        "behind": 0,
    }
    accepted = client.post(
        f"/api/v1/agent/copies/{copy['id']}/observations", headers=dh, json=payload
    )
    assert accepted.status_code == 200 and accepted.json()["accepted"]

    latest = client.get(f"/api/v1/projects/{p['id']}/copies", headers=h).json()[0]
    # Observation fields advanced, binding fields preserved exactly.
    assert latest["dirty"] and latest["sequence"] == 1
    assert latest["repository_id"] == repo["id"]
    assert latest["binding_revision"] == 1
