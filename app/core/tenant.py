from typing import Annotated

from fastapi import Depends, Header, HTTPException, Query, status

from app.core.config import get_settings


def resolve_tenant(
    x_tenant_id: Annotated[str | None, Header(alias="X-Tenant-ID")] = None,
    tenant: Annotated[
        str | None,
        Query(
            description="Tenant id (assessment contract). Must match X-Tenant-ID when both are set.",
        ),
    ] = None,
) -> str:
    """Resolve tenant from header and/or query param.

    Supports ``GET /search?q=&tenant=`` while also allowing header-based tenancy
    used across document routes.
    """
    header = x_tenant_id.strip() if x_tenant_id and x_tenant_id.strip() else None
    query = tenant.strip() if tenant and tenant.strip() else None

    if header and query and header != query:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query param tenant must match X-Tenant-ID header",
        )

    resolved = header or query
    if not resolved:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Missing tenant: provide {get_settings().tenant_header} header "
                "and/or tenant query parameter"
            ),
        )
    return resolved


TenantId = Annotated[str, Depends(resolve_tenant)]
