from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DocumentCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    content: str = Field(..., min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: str
    title: str
    content: str
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class SearchHit(BaseModel):
    id: UUID
    title: str
    snippet: str
    score: float
    highlight: str | None = None


class SearchResponse(BaseModel):
    query: str
    tenant_id: str
    results: list[SearchHit]
    total: int
    took_ms: float
    cached: bool = False


class HealthDependency(BaseModel):
    status: str
    detail: str | None = None


class HealthResponse(BaseModel):
    status: str
    postgres: HealthDependency
    redis: HealthDependency
