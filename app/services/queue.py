import json
import uuid

import redis.asyncio as redis

from app.core.config import get_settings


async def enqueue_index_job(
    client: redis.Redis,
    *,
    document_id: uuid.UUID,
    tenant_id: str,
    action: str,
) -> str:
    """Publish an indexing job to Redis Streams (eventually consistent search)."""
    settings = get_settings()
    message_id = await client.xadd(
        settings.index_stream,
        {
            "document_id": str(document_id),
            "tenant_id": tenant_id,
            "action": action,
            "payload": json.dumps({"document_id": str(document_id), "tenant_id": tenant_id}),
        },
    )
    return message_id
