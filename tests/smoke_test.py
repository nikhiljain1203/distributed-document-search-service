"""Smoke tests against a running stack (docker compose up)."""

from __future__ import annotations

import os
import time
import uuid

import httpx
import pytest

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
TENANT = f"test-{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="module")
def client() -> httpx.Client:
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as c:
        for _ in range(30):
            try:
                r = c.get("/health")
                if r.status_code == 200 and r.json().get("status") == "ok":
                    break
            except httpx.HTTPError:
                pass
            time.sleep(1)
        else:
            pytest.skip(f"API not healthy at {BASE_URL}")
        yield c


def test_health(client: httpx.Client) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["postgres"]["status"] == "up"
    assert body["redis"]["status"] == "up"


def test_document_lifecycle_and_search(client: httpx.Client) -> None:
    headers = {"X-Tenant-ID": TENANT}
    create = client.post(
        "/documents",
        headers=headers,
        json={
            "title": "Distributed search primer",
            "content": "Full-text ranking, caching, and tenant isolation patterns.",
            "metadata": {"suite": "smoke"},
        },
    )
    assert create.status_code == 201, create.text
    doc = create.json()
    doc_id = doc["id"]

    got = client.get(f"/documents/{doc_id}", headers=headers)
    assert got.status_code == 200
    assert got.json()["title"] == "Distributed search primer"

    other = client.get(f"/documents/{doc_id}", headers={"X-Tenant-ID": "someone-else"})
    assert other.status_code == 404

    search = client.get("/search", params={"q": "ranking", "tenant": TENANT}, headers=headers)
    assert search.status_code == 200, search.text
    payload = search.json()
    assert payload["total"] >= 1
    assert any(hit["id"] == doc_id for hit in payload["results"])
    assert payload["results"][0].get("highlight")

    search2 = client.get("/search", params={"q": "ranking", "tenant": TENANT}, headers=headers)
    assert search2.status_code == 200
    assert search2.json()["cached"] is True

    deleted = client.delete(f"/documents/{doc_id}", headers=headers)
    assert deleted.status_code == 204

    missing = client.get(f"/documents/{doc_id}", headers=headers)
    assert missing.status_code == 404


def test_search_with_tenant_query_param_only(client: httpx.Client) -> None:
    """Assessment contract: GET /search?q={query}&tenant={tenantId}."""
    tenant = f"query-{uuid.uuid4().hex[:8]}"
    created = client.post(
        "/documents",
        headers={"X-Tenant-ID": tenant},
        json={"title": "OpenSearch notes", "content": "Shard allocation and replicas"},
    )
    assert created.status_code == 201

    search = client.get("/search", params={"q": "OpenSearch", "tenant": tenant})
    assert search.status_code == 200, search.text
    assert search.json()["total"] >= 1


def test_missing_tenant_rejected(client: httpx.Client) -> None:
    r = client.get("/search", params={"q": "test"})
    assert r.status_code == 400


def test_tenant_mismatch_rejected(client: httpx.Client) -> None:
    r = client.get(
        "/search",
        params={"q": "test", "tenant": "a"},
        headers={"X-Tenant-ID": "b"},
    )
    assert r.status_code == 400


def test_fuzzy_search(client: httpx.Client) -> None:
    tenant = f"fuzzy-{uuid.uuid4().hex[:8]}"
    created = client.post(
        "/documents",
        headers={"X-Tenant-ID": tenant},
        json={"title": "Elasticsearch guide", "content": "Analyzers and inverted indexes"},
    )
    assert created.status_code == 201
    search = client.get("/search", params={"q": "Elastcsearch", "tenant": tenant})
    assert search.status_code == 200
    assert search.json()["total"] >= 1


def test_rate_limit_returns_429(client: httpx.Client) -> None:
    """Pre-seed Redis counter to the limit so the next request is rejected."""
    import subprocess

    tenant = f"rl-{uuid.uuid4().hex[:8]}"
    limit = int(os.getenv("RATE_LIMIT_PER_MINUTE", "100"))
    window = int(time.time() // 60)
    key = f"rl:{tenant}:{window}"

    # Prefer dockerized Redis from compose; fall back to local redis-cli.
    seed_cmds = [
        ["docker", "compose", "exec", "-T", "redis", "redis-cli", "SET", key, str(limit), "EX", "70"],
        ["redis-cli", "SET", key, str(limit), "EX", "70"],
    ]
    seeded = False
    for cmd in seed_cmds:
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True, cwd=os.getcwd())
            seeded = True
            break
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue
    if not seeded:
        pytest.skip("Could not seed Redis rate-limit key")

    resp = client.get("/search", params={"q": "x", "tenant": tenant})
    assert resp.status_code == 429
    assert "Rate limit" in resp.json()["detail"]
