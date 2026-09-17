import logging
import time
import uuid

import redis.asyncio as redis
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cache_get, cache_set, search_cache_key
from app.schemas import SearchHit, SearchResponse

logger = logging.getLogger(__name__)


def _snippet(content: str, query: str, max_len: int = 180) -> str:
    lower = content.lower()
    terms = [t for t in query.lower().split() if t]
    pos = -1
    for term in terms:
        pos = lower.find(term)
        if pos >= 0:
            break
    if pos < 0:
        return content[:max_len] + ("…" if len(content) > max_len else "")
    start = max(0, pos - 40)
    end = min(len(content), start + max_len)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(content) else ""
    return f"{prefix}{content[start:end]}{suffix}"


def _highlight(title: str, content: str, query: str) -> str:
    terms = [t for t in query.split() if t]
    haystack = f"{title} — {content[:240]}"
    out = haystack
    for term in terms:
        idx = out.lower().find(term.lower())
        if idx >= 0:
            matched = out[idx : idx + len(term)]
            out = out[:idx] + f"<em>{matched}</em>" + out[idx + len(term) :]
    return out


_SEARCH_SQL = """
WITH q AS (
    SELECT
        NULLIF(websearch_to_tsquery('english', :q), ''::tsquery) AS tsq,
        :q AS raw
)
SELECT
    d.id,
    d.title,
    d.content,
    CASE
        WHEN q.tsq IS NOT NULL AND d.search_vector @@ q.tsq
            THEN ts_rank_cd(d.search_vector, q.tsq)
        ELSE similarity(d.title, q.raw) * 0.5
    END AS score
FROM documents d, q
WHERE d.tenant_id = :tenant_id
  AND (
        (q.tsq IS NOT NULL AND d.search_vector @@ q.tsq)
        OR similarity(d.title, q.raw) > 0.25
      )
ORDER BY score DESC, d.created_at DESC
LIMIT :limit OFFSET :offset
"""

_COUNT_SQL = """
WITH q AS (
    SELECT
        NULLIF(websearch_to_tsquery('english', :q), ''::tsquery) AS tsq,
        :q AS raw
)
SELECT COUNT(*) AS total
FROM documents d, q
WHERE d.tenant_id = :tenant_id
  AND (
        (q.tsq IS NOT NULL AND d.search_vector @@ q.tsq)
        OR similarity(d.title, q.raw) > 0.25
      )
"""

_FUZZY_ONLY_SQL = """
SELECT
    d.id,
    d.title,
    d.content,
    similarity(d.title, :q) * 0.5 AS score
FROM documents d
WHERE d.tenant_id = :tenant_id
  AND similarity(d.title, :q) > 0.2
ORDER BY score DESC, d.created_at DESC
LIMIT :limit OFFSET :offset
"""

_FUZZY_COUNT_SQL = """
SELECT COUNT(*) AS total
FROM documents d
WHERE d.tenant_id = :tenant_id
  AND similarity(d.title, :q) > 0.2
"""


async def search_documents(
    session: AsyncSession,
    redis_client: redis.Redis,
    tenant_id: str,
    q: str,
    limit: int = 10,
    offset: int = 0,
) -> SearchResponse:
    started = time.perf_counter()
    cache_key = search_cache_key(tenant_id, q, limit, offset)
    cached = await cache_get(redis_client, cache_key)
    if cached is not None:
        response = SearchResponse.model_validate(cached)
        response.cached = True
        response.took_ms = round((time.perf_counter() - started) * 1000, 2)
        return response

    params = {"q": q, "tenant_id": tenant_id, "limit": limit, "offset": offset}
    try:
        rows = (await session.execute(text(_SEARCH_SQL), params)).mappings().all()
        count_row = (await session.execute(text(_COUNT_SQL), params)).mappings().one()
    except SQLAlchemyError:
        # Invalid websearch syntax / empty tsquery edge cases → fuzzy-only fallback.
        logger.warning("FTS query failed for q=%r; falling back to trigram search", q)
        await session.rollback()
        rows = (await session.execute(text(_FUZZY_ONLY_SQL), params)).mappings().all()
        count_row = (await session.execute(text(_FUZZY_COUNT_SQL), params)).mappings().one()

    hits = [
        SearchHit(
            id=uuid.UUID(str(row["id"])),
            title=row["title"],
            snippet=_snippet(row["content"], q),
            score=float(row["score"] or 0.0),
            highlight=_highlight(row["title"], row["content"], q),
        )
        for row in rows
    ]

    response = SearchResponse(
        query=q,
        tenant_id=tenant_id,
        results=hits,
        total=int(count_row["total"]),
        took_ms=round((time.perf_counter() - started) * 1000, 2),
        cached=False,
    )
    await cache_set(redis_client, cache_key, response.model_dump(mode="json"))
    return response
