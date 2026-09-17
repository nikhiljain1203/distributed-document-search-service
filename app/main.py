from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import documents, health, search
from app.core.config import get_settings
from app.core.redis_client import close_redis


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await close_redis()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        description=(
            "Multi-tenant distributed document search prototype with PostgreSQL FTS, "
            "Redis caching/rate limiting, and async indexing via Redis Streams."
        ),
        lifespan=lifespan,
    )
    app.include_router(health.router)
    app.include_router(documents.router)
    app.include_router(search.router)
    return app


app = create_app()
