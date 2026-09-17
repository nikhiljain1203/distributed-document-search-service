"""Async indexer worker: consumes Redis Streams and maintains search_vector."""

from __future__ import annotations

import asyncio
import logging
import signal

import redis.asyncio as redis
from sqlalchemy import text

from app.core.config import get_settings
from app.core.redis_client import close_redis, get_redis_client
from app.db.session import SessionLocal

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("indexer")


async def ensure_consumer_group(client: redis.Redis) -> None:
    settings = get_settings()
    try:
        await client.xgroup_create(settings.index_stream, settings.index_group, id="0", mkstream=True)
        logger.info("Created consumer group %s on %s", settings.index_group, settings.index_stream)
    except redis.ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


async def reindex_document(document_id: str, tenant_id: str) -> None:
    async with SessionLocal() as session:
        await session.execute(
            text(
                """
                UPDATE documents
                SET search_vector =
                    setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
                    setweight(to_tsvector('english', coalesce(content, '')), 'B'),
                    updated_at = NOW()
                WHERE id = CAST(:id AS uuid) AND tenant_id = :tenant_id
                """
            ),
            {"id": document_id, "tenant_id": tenant_id},
        )
        await session.commit()
        logger.info("Reindexed document %s for tenant %s", document_id, tenant_id)


async def process_message(fields: dict[str, str]) -> None:
    action = fields.get("action", "upsert")
    document_id = fields.get("document_id")
    tenant_id = fields.get("tenant_id")
    if not document_id or not tenant_id:
        logger.warning("Skipping malformed message: %s", fields)
        return

    if action == "delete":
        # Document row already removed; acknowledge only.
        logger.info("Acknowledged delete for document %s tenant %s", document_id, tenant_id)
        return

    await reindex_document(document_id, tenant_id)


async def run_worker(stop_event: asyncio.Event) -> None:
    settings = get_settings()
    client = await get_redis_client()
    await ensure_consumer_group(client)

    logger.info(
        "Indexer listening on stream=%s group=%s consumer=%s",
        settings.index_stream,
        settings.index_group,
        settings.index_consumer,
    )

    while not stop_event.is_set():
        messages = await client.xreadgroup(
            groupname=settings.index_group,
            consumername=settings.index_consumer,
            streams={settings.index_stream: ">"},
            count=10,
            block=2000,
        )
        if not messages:
            continue

        for _stream_name, entries in messages:
            for message_id, fields in entries:
                try:
                    await process_message(fields)
                    await client.xack(settings.index_stream, settings.index_group, message_id)
                except Exception:  # noqa: BLE001
                    logger.exception("Failed processing message %s", message_id)


async def main() -> None:
    stop_event = asyncio.Event()

    def _handle_signal(*_: object) -> None:
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _handle_signal)
        except NotImplementedError:
            signal.signal(sig, lambda *_: stop_event.set())

    try:
        await run_worker(stop_event)
    finally:
        await close_redis()
        logger.info("Indexer shut down")


if __name__ == "__main__":
    asyncio.run(main())
