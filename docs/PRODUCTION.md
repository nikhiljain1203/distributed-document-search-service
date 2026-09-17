# Production Readiness Analysis

What this prototype would need before serving millions of documents at enterprise SLAs.

## Scalability (100x documents and traffic)

- **Search plane:** migrate FTS to an OpenSearch cluster; shard by tenant hash or time; use index aliases for blue/green reindex.
- **Write path:** keep Postgres (or partitioned Postgres) as system of record; stream CDC (Debezium) into the search cluster to avoid dual-write bugs.
- **Read path:** API replicas behind an L7 load balancer; Redis Cluster for cache; optional edge cache for anonymized public queries.
- **Tenants:** isolate hot tenants onto dedicated index templates / compute pools; enforce per-tenant quotas and burst tokens.
- **Data growth:** partition documents by tenant + month; archive cold content to object storage with searchable stubs.

## Resilience

- Timeouts and deadlines on every dependency call (Postgres, Redis, OpenSearch).
- Retries with exponential backoff + jitter for idempotent reads; bounded retries for writes with idempotency keys.
- Circuit breakers around search backends; degrade to “metadata-only” or cached results when open.
- Queue DLQ + replay tooling; poison-message quarantine.
- Multi-AZ deployment; automated failover for Postgres (Patroni / RDS Multi-AZ) and Redis (sentinel/cluster).
- Chaos experiments for dependency loss and partition scenarios.

## Security

- Replace header-only tenancy with OAuth2/OIDC JWT; bind `tenant_id` from verified claims, never from client-controlled headers alone.
- RBAC: roles for index, search, admin; ABAC for document ACLs inside a tenant.
- TLS everywhere; mTLS for service-to-service traffic.
- Encryption at rest (Postgres TDE / cloud KMS; Redis AUTH + encryption).
- Input validation, max payload sizes, WAF rate limits, audit logging of mutations.
- Regular dependency scanning and secrets management (no credentials in images).

## Observability

- **Metrics:** RED (rate, errors, duration) per endpoint; cache hit ratio; rate-limit rejections; stream lag; FTS/OpenSearch p50/p95/p99.
- **Logs:** structured JSON with `request_id`, `tenant_id`, `document_id`; never log raw document bodies in prod by default.
- **Tracing:** OpenTelemetry across API → Redis → Postgres/OpenSearch → worker.
- **Alerts:** error budget burn, lag SLO, disk saturation, replica lag, certificate expiry.

## Performance

- Connection pooling (PgBouncer); prepared statements; covering indexes for common filters.
- OpenSearch: force-merge policy for read-heavy indexes; careful refresh interval vs indexing latency.
- Query budgets: reject pathological boolean queries; truncate offsets; prefer search-after/cursors.
- Benchmark with realistic tenant skew (Zipf) not uniform load.
- Keep p95 search < 500ms via warm caches, replica reads, and avoiding deep pagination.

## Operations

- GitOps / CI: build, test, migrate, canary, promote.
- Zero-downtime: rolling updates for API/workers; blue-green or dual-write reindex for schema/analyzer changes.
- Backups: Postgres PITR; Redis AOF/RDB as cache-only (rebuildable); OpenSearch snapshots to object storage.
- Runbooks for: search cluster yellow/red, cache stampede, poison index jobs, tenant noisy neighbor.
- Cost controls: index lifecycle management (hot/warm/cold), right-size replicas, cache TTLs tuned to hit rate.

## SLA considerations (99.95% availability)

- Monthly error budget ≈ 22 minutes; gate releases on burn rate.
- N+1 capacity in each AZ; RPO near-zero for metadata (sync replicas), RTO < 15 minutes with automated failover.
- Dependency SLOs composed carefully—cache misses must not cascade into search overload (bulkheads + load shedding).
- Synthetic probes for `/health` and a canary search query per critical tenant tier.
- Status page + customer communication playbooks when budget is burned.

## Cost optimization (bonus)

- Prefer OpenSearch Serverless or reserved nodes only after steady-state sizing.
- Aggressive ILM for infrequently searched tenants.
- Cache hot queries to cut search CU / CPU.
- Compress document bodies; store large attachments in S3 with pointers in Postgres.
