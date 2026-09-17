import redis.asyncio as redis
from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_client import get_redis
from app.db.session import get_db
from app.schemas import HealthDependency, HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(
    response: Response,
    db: AsyncSession = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),
) -> HealthResponse:
    pg_status = HealthDependency(status="up")
    redis_status = HealthDependency(status="up")

    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - health must catch all dependency failures
        pg_status = HealthDependency(status="down", detail=str(exc))

    try:
        pong = await redis_client.ping()
        if not pong:
            redis_status = HealthDependency(status="down", detail="PING returned false")
    except Exception as exc:  # noqa: BLE001
        redis_status = HealthDependency(status="down", detail=str(exc))

    overall = "ok" if pg_status.status == "up" and redis_status.status == "up" else "degraded"
    if overall != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(status=overall, postgres=pg_status, redis=redis_status)
