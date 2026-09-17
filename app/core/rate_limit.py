import logging
import time

import redis.asyncio as redis
from fastapi import Depends, HTTPException, status

from app.core.config import get_settings
from app.core.redis_client import get_redis
from app.core.tenant import TenantId

logger = logging.getLogger(__name__)


async def enforce_rate_limit(client: redis.Redis, tenant_id: str) -> None:
    """Fixed-window rate limiter: N requests per calendar minute per tenant."""
    limit = get_settings().rate_limit_per_minute
    window = int(time.time() // 60)
    key = f"rl:{tenant_id}:{window}"

    try:
        count = await client.incr(key)
        if count == 1:
            await client.expire(key, 70)
    except redis.RedisError:
        # Fail open if Redis is unavailable so search/CRUD can still proceed.
        logger.warning("Rate limiter unavailable; allowing request for tenant=%s", tenant_id)
        return

    if count > limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded for tenant '{tenant_id}' ({limit}/min)",
            headers={"Retry-After": "60"},
        )


async def rate_limit_tenant(
    tenant_id: TenantId,
    redis_client: redis.Redis = Depends(get_redis),
) -> str:
    """FastAPI dependency: enforce per-tenant rate limit, return tenant id."""
    await enforce_rate_limit(redis_client, tenant_id)
    return tenant_id
