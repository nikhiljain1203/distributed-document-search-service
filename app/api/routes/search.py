import redis.asyncio as redis
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import rate_limit_tenant
from app.core.redis_client import get_redis
from app.db.session import get_db
from app.schemas import SearchResponse
from app.services import search as search_service

router = APIRouter(tags=["search"])


@router.get("/search", response_model=SearchResponse)
async def search(
    q: str = Query(..., min_length=1, description="Full-text search query"),
    limit: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    tenant_id: str = Depends(rate_limit_tenant),
    db: AsyncSession = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),
) -> SearchResponse:
    """Search documents for a tenant.

    Tenant may be supplied via ``X-Tenant-ID`` and/or ``?tenant=`` (assessment contract).
    """
    return await search_service.search_documents(
        db, redis_client, tenant_id, q=q.strip(), limit=limit, offset=offset
    )
