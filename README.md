# Distributed Document Search Service

Prototype multi-tenant document search API with PostgreSQL full-text search, Redis caching/rate limiting, and async indexing via Redis Streams.

## Quick start

```bash
docker compose up --build -d
curl http://localhost:8000/health
```

API docs: http://localhost:8000/docs

## Required tenant identity

Document and search routes require a tenant via **`X-Tenant-ID` header** and/or **`tenant` query parameter** (assessment contract: `GET /search?q={query}&tenant={tenantId}`). If both are provided they must match.

## Sample requests

```bash
./scripts/sample_requests.sh
```

Postman: import [`scripts/postman_collection.json`](scripts/postman_collection.json)

```bash
# Index a document
curl -s -X POST http://localhost:8000/documents \
  -H 'Content-Type: application/json' \
  -H 'X-Tenant-ID: acme' \
  -d '{"title":"Kubernetes basics","content":"Pods, services, and deployments","metadata":{"lang":"en"}}'

# Search — query-param tenant (assessment contract)
curl -s 'http://localhost:8000/search?q=kubernetes&tenant=acme'

# Search — header tenant
curl -s 'http://localhost:8000/search?q=kubernetes' -H 'X-Tenant-ID: acme'

# Get / delete
curl -s http://localhost:8000/documents/<id> -H 'X-Tenant-ID: acme'
curl -s -X DELETE http://localhost:8000/documents/<id> -H 'X-Tenant-ID: acme'
```

## Documentation (assessment deliverables)

| Deliverable | Location |
|-------------|----------|
| **Single submission doc** (architecture + production + experience + AI usage) | [docs/SUBMISSION.md](docs/SUBMISSION.md) |
| Architecture (also standalone) | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| Production readiness | [docs/PRODUCTION.md](docs/PRODUCTION.md) |
| Experience showcase (fill before submit) | [docs/EXPERIENCE.md](docs/EXPERIENCE.md) |

## Stack

| Component | Technology |
|-----------|------------|
| API | FastAPI (Python 3.12) |
| Source of truth + FTS | PostgreSQL 16 (`tsvector` / `ts_rank` + `pg_trgm`) |
| Cache / rate limit / queue | Redis 7 |
| Indexer | Redis Streams consumer worker |
| Packaging | Docker Compose |

## Assumptions

- Single-region prototype; one Postgres instance
- Tenants are auto-created on first write
- Auth is tenant header/query isolation only (no JWT in prototype)
- Search index is written synchronously on insert and re-asserted asynchronously by the worker
- Cache/rate-limit Redis failures degrade gracefully (fail-open limiter, cache miss)
- Experience showcase in `docs/EXPERIENCE.md` / `docs/SUBMISSION.md` should be filled with your real anecdotes before submission

## AI tool usage

Built with Cursor (Composer) assistance for scaffolding, API wiring, Docker Compose, documentation, and review/gap fixes. Design decisions and production analysis were curated for this assessment.

## Local smoke test

With the stack running:

```bash
pip install -r requirements.txt
pytest -q
```
