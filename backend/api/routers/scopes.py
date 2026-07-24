"""
CRUD endpoints for product scopes (categories/watchlists).
Also manages the scope↔source links (scope_sources junction).
"""

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.db.models import Product, ProductScope, ScopeSource, Source
from backend.db.session import get_session_dependency

router = APIRouter()


# --- Schemas ---

class ScopeCreate(BaseModel):
    name: str
    slug: str
    description: str | None = None
    qualifier_rules: dict[str, Any] = {}
    search_terms: list[str] = []
    min_price_eur: float | None = None
    max_price_eur: float | None = None
    is_active: bool = True


class ScopeUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    qualifier_rules: dict[str, Any] | None = None
    search_terms: list[str] | None = None
    min_price_eur: float | None = None
    max_price_eur: float | None = None
    is_active: bool | None = None


class ScopeResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    description: str | None
    qualifier_rules: dict[str, Any]
    search_terms: list[str]
    min_price_eur: float | None
    max_price_eur: float | None
    is_active: bool
    created_at: datetime
    product_count: int = 0

    model_config = {"from_attributes": True}


# --- Endpoints ---

@router.get("", response_model=list[ScopeResponse])
async def list_scopes(
    active_only: bool = False,
    db: AsyncSession = Depends(get_session_dependency),
):
    q = select(ProductScope)
    if active_only:
        q = q.where(ProductScope.is_active == True)
    result = await db.execute(q)
    scopes = result.scalars().all()

    out = []
    for scope in scopes:
        count_result = await db.execute(
            select(Product).where(
                Product.scope_id == scope.id, Product.status == "active"
            )
        )
        count = len(count_result.scalars().all())
        data = ScopeResponse.model_validate(scope)
        data.product_count = count
        out.append(data)
    return out


@router.post("", response_model=ScopeResponse, status_code=201)
async def create_scope(
    body: ScopeCreate, db: AsyncSession = Depends(get_session_dependency)
):
    existing = await db.execute(
        select(ProductScope).where(ProductScope.slug == body.slug)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(400, f"Slug '{body.slug}' already exists")
    scope = ProductScope(**body.model_dump())
    db.add(scope)
    await db.flush()
    return ScopeResponse.model_validate(scope)


@router.get("/{scope_id}", response_model=ScopeResponse)
async def get_scope(
    scope_id: uuid.UUID, db: AsyncSession = Depends(get_session_dependency)
):
    result = await db.execute(
        select(ProductScope).where(ProductScope.id == scope_id)
    )
    scope = result.scalar_one_or_none()
    if not scope:
        raise HTTPException(404, "Scope not found")
    return ScopeResponse.model_validate(scope)


@router.patch("/{scope_id}", response_model=ScopeResponse)
async def update_scope(
    scope_id: uuid.UUID,
    body: ScopeUpdate,
    db: AsyncSession = Depends(get_session_dependency),
):
    result = await db.execute(
        select(ProductScope).where(ProductScope.id == scope_id)
    )
    scope = result.scalar_one_or_none()
    if not scope:
        raise HTTPException(404, "Scope not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(scope, field, value)
    return ScopeResponse.model_validate(scope)


@router.delete("/{scope_id}", status_code=204)
async def delete_scope(
    scope_id: uuid.UUID, db: AsyncSession = Depends(get_session_dependency)
):
    result = await db.execute(
        select(ProductScope).where(ProductScope.id == scope_id)
    )
    scope = result.scalar_one_or_none()
    if not scope:
        raise HTTPException(404, "Scope not found")
    await db.delete(scope)


# ---------------------------------------------------------------------------
# Scope ↔ Source link management
# ---------------------------------------------------------------------------

class ScopeSourceOut(BaseModel):
    id: uuid.UUID
    source_id: uuid.UUID
    source_name: str
    source_slug: str
    base_url: str
    search_url_template: str | None
    is_active: bool

    model_config = {"from_attributes": True}


class ScopeSourceLink(BaseModel):
    source_id: uuid.UUID
    search_url_template: str | None = None
    is_active: bool = True


@router.get("/{scope_id}/sources", response_model=list[ScopeSourceOut])
async def list_scope_sources(
    scope_id: uuid.UUID, db: AsyncSession = Depends(get_session_dependency)
):
    result = await db.execute(
        select(ScopeSource)
        .where(ScopeSource.scope_id == scope_id)
        .options(selectinload(ScopeSource.source))
    )
    links = result.scalars().all()
    return [
        ScopeSourceOut(
            id=lnk.id,
            source_id=lnk.source_id,
            source_name=lnk.source.name if lnk.source else "",
            source_slug=lnk.source.slug if lnk.source else "",
            base_url=lnk.source.base_url if lnk.source else "",
            search_url_template=lnk.search_url_template,
            is_active=lnk.is_active,
        )
        for lnk in links
    ]


@router.post("/{scope_id}/sources", response_model=ScopeSourceOut, status_code=201)
async def link_source_to_scope(
    scope_id: uuid.UUID,
    body: ScopeSourceLink,
    db: AsyncSession = Depends(get_session_dependency),
):
    # Verify scope exists
    scope = (await db.execute(select(ProductScope).where(ProductScope.id == scope_id))).scalar_one_or_none()
    if not scope:
        raise HTTPException(404, "Scope not found")

    # Verify source exists
    source = (await db.execute(select(Source).where(Source.id == body.source_id))).scalar_one_or_none()
    if not source:
        raise HTTPException(404, "Source not found")

    # Check for existing link
    existing = (await db.execute(
        select(ScopeSource).where(
            ScopeSource.scope_id == scope_id,
            ScopeSource.source_id == body.source_id,
        )
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(409, "Source already linked to this scope")

    link = ScopeSource(
        scope_id=scope_id,
        source_id=body.source_id,
        search_url_template=body.search_url_template,
        is_active=body.is_active,
    )
    db.add(link)
    await db.flush()
    return ScopeSourceOut(
        id=link.id,
        source_id=link.source_id,
        source_name=source.name,
        source_slug=source.slug,
        base_url=source.base_url,
        search_url_template=link.search_url_template,
        is_active=link.is_active,
    )


@router.delete("/{scope_id}/sources/{source_id}", status_code=204)
async def unlink_source_from_scope(
    scope_id: uuid.UUID,
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_session_dependency),
):
    link = (await db.execute(
        select(ScopeSource).where(
            ScopeSource.scope_id == scope_id,
            ScopeSource.source_id == source_id,
        )
    )).scalar_one_or_none()
    if not link:
        raise HTTPException(404, "Link not found")
    await db.delete(link)
