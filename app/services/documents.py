import json
import logging
import uuid

import redis.asyncio as redis
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import (
    cache_get,
    cache_set,
    doc_cache_key,
    invalidate_doc_cache,
    invalidate_tenant_search_cache,
)
from app.db.models import Document, Tenant
from app.schemas import DocumentCreate, DocumentResponse
from app.services.queue import enqueue_index_job

logger = logging.getLogger(__name__)


async def ensure_tenant(session: AsyncSession, tenant_id: str) -> Tenant:
    result = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if tenant:
        return tenant
    tenant = Tenant(id=tenant_id, name=tenant_id)
    session.add(tenant)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        result = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
        tenant = result.scalar_one()
    return tenant


def _to_response(doc: Document) -> DocumentResponse:
    return DocumentResponse(
        id=doc.id,
        tenant_id=doc.tenant_id,
        title=doc.title,
        content=doc.content,
        metadata=doc.metadata_ or {},
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


async def _best_effort_post_write(
    redis_client: redis.Redis,
    *,
    tenant_id: str,
    document_id: uuid.UUID,
    action: str,
) -> None:
    try:
        if action == "delete":
            await invalidate_doc_cache(redis_client, tenant_id, str(document_id))
        await invalidate_tenant_search_cache(redis_client, tenant_id)
        await enqueue_index_job(
            redis_client, document_id=document_id, tenant_id=tenant_id, action=action
        )
    except Exception:  # noqa: BLE001 - document write already committed
        logger.exception(
            "Post-write side effects failed action=%s tenant=%s doc=%s",
            action,
            tenant_id,
            document_id,
        )


async def create_document(
    session: AsyncSession,
    redis_client: redis.Redis,
    tenant_id: str,
    payload: DocumentCreate,
) -> DocumentResponse:
    await ensure_tenant(session, tenant_id)
    doc_id = uuid.uuid4()

    # Single round-trip: insert + weighted FTS vector for immediate findability.
    await session.execute(
        text(
            """
            INSERT INTO documents (id, tenant_id, title, content, metadata, search_vector, created_at, updated_at)
            VALUES (
                :id,
                :tenant_id,
                :title,
                :content,
                CAST(:metadata AS jsonb),
                setweight(to_tsvector('english', coalesce(:title, '')), 'A') ||
                setweight(to_tsvector('english', coalesce(:content, '')), 'B'),
                NOW(),
                NOW()
            )
            """
        ),
        {
            "id": doc_id,
            "tenant_id": tenant_id,
            "title": payload.title,
            "content": payload.content,
            "metadata": json.dumps(payload.metadata or {}),
        },
    )
    await session.commit()

    result = await session.execute(
        select(Document).where(Document.id == doc_id, Document.tenant_id == tenant_id)
    )
    doc = result.scalar_one()
    await _best_effort_post_write(
        redis_client, tenant_id=tenant_id, document_id=doc.id, action="upsert"
    )
    return _to_response(doc)


async def get_document(
    session: AsyncSession,
    redis_client: redis.Redis,
    tenant_id: str,
    document_id: uuid.UUID,
) -> DocumentResponse | None:
    cache_key = doc_cache_key(tenant_id, str(document_id))
    cached = await cache_get(redis_client, cache_key)
    if cached is not None:
        return DocumentResponse.model_validate(cached)

    result = await session.execute(
        select(Document).where(Document.id == document_id, Document.tenant_id == tenant_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        return None

    response = _to_response(doc)
    await cache_set(redis_client, cache_key, response.model_dump(mode="json"))
    return response


async def delete_document(
    session: AsyncSession,
    redis_client: redis.Redis,
    tenant_id: str,
    document_id: uuid.UUID,
) -> bool:
    result = await session.execute(
        select(Document).where(Document.id == document_id, Document.tenant_id == tenant_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        return False

    await session.delete(doc)
    await session.commit()
    await _best_effort_post_write(
        redis_client, tenant_id=tenant_id, document_id=document_id, action="delete"
    )
    return True
