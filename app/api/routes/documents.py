from uuid import UUID

import redis.asyncio as redis
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import rate_limit_tenant
from app.core.redis_client import get_redis
from app.db.session import get_db
from app.schemas import DocumentCreate, DocumentResponse
from app.services import documents as document_service

router = APIRouter(tags=["documents"])


@router.post("/documents", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def create_document(
    payload: DocumentCreate,
    tenant_id: str = Depends(rate_limit_tenant),
    db: AsyncSession = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),
) -> DocumentResponse:
    return await document_service.create_document(db, redis_client, tenant_id, payload)


@router.get("/documents/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: UUID,
    tenant_id: str = Depends(rate_limit_tenant),
    db: AsyncSession = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),
) -> DocumentResponse:
    doc = await document_service.get_document(db, redis_client, tenant_id, document_id)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return doc


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: UUID,
    tenant_id: str = Depends(rate_limit_tenant),
    db: AsyncSession = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),
) -> None:
    deleted = await document_service.delete_document(db, redis_client, tenant_id, document_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
