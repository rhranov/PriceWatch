"""
SQLAlchemy 2.0 ORM models — fully generalized for any product category.

Schema overview:
  product_scopes       → categories/watchlists (e.g. "AI Hardware", "Gaming GPUs")
  sources              → websites to scrape (idealo, amazon.de, etc.)
  scope_sources        → which sources to use per scope
  products             → specific products on the watchlist
  product_listings     → one URL per product per source
  price_history        → time-series price records
  pending_discoveries  → new products found, awaiting user approval
  agent_runs           → log of every daily pipeline execution
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Product Scopes (categories / watchlists)
# ---------------------------------------------------------------------------


class ProductScope(Base):
    """
    A product scope defines a category of products to watch.

    qualifier_rules (JSONB): Rules the AI qualifier agent uses to decide
        if a candidate product belongs to this scope.
        Example for AI Hardware:
            {
              "min_unified_memory_gb": 128,
              "cpu_gpu_unified": true,
              "must_ship_to_germany": true,
              "description": "128GB+ unified memory, CPU+GPU on same chip, runs LLMs locally"
            }

    search_terms (JSONB array): Search strings used by the research agent.
        Example: ["128GB unified memory mini PC", "DGX Spark alternative",
                  "AMD Ryzen AI Max 395 mini PC", "Strix Halo desktop"]
    """

    __tablename__ = "product_scopes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    qualifier_rules: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    search_terms: Mapped[list[str]] = mapped_column(JSONB, default=list)
    min_price_eur: Mapped[float | None] = mapped_column(Float)
    max_price_eur: Mapped[float | None] = mapped_column(Float)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    products: Mapped[list["Product"]] = relationship(
        back_populates="scope", cascade="all, delete-orphan"
    )
    scope_sources: Mapped[list["ScopeSource"]] = relationship(
        back_populates="scope", cascade="all, delete-orphan"
    )
    pending_discoveries: Mapped[list["PendingDiscovery"]] = relationship(
        back_populates="scope", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# Sources (websites to scrape)
# ---------------------------------------------------------------------------


class Source(Base):
    """
    A data source (website) that can be scraped for products.
    """

    __tablename__ = "sources"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    scraper_type: Mapped[str] = mapped_column(
        String(50), default="playwright"
    )  # playwright | httpx
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    rate_limit_seconds: Mapped[float] = mapped_column(Float, default=5.0)
    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict
    )  # source-specific scraper config
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    scope_sources: Mapped[list["ScopeSource"]] = relationship(back_populates="source")
    listings: Mapped[list["ProductListing"]] = relationship(back_populates="source")


class ScopeSource(Base):
    """
    Junction: which sources are used for which scope, with scope-specific search config.
    """

    __tablename__ = "scope_sources"
    __table_args__ = (UniqueConstraint("scope_id", "source_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    scope_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("product_scopes.id", ondelete="CASCADE")
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE")
    )
    search_url_template: Mapped[str | None] = mapped_column(
        String(1000)
    )  # {query} placeholder
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    scope: Mapped["ProductScope"] = relationship(back_populates="scope_sources")
    source: Mapped["Source"] = relationship(back_populates="scope_sources")


# ---------------------------------------------------------------------------
# Products (the watchlist)
# ---------------------------------------------------------------------------


class Product(Base):
    """
    A specific product being monitored.
    specs (JSONB) stores scope-specific attributes flexibly:
      - AI Hardware: {unified_memory_gb: 128, chip: "Grace Blackwell GB10", tdp_watts: 60}
      - Gaming GPU:  {vram_gb: 24, gpu_model: "RTX 5090", tdp_watts: 575}
    """

    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    scope_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("product_scopes.id", ondelete="RESTRICT")
    )
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(200))
    model: Mapped[str | None] = mapped_column(String(200))
    specs: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(
        String(50), default="active"
    )  # active | paused | discontinued
    notes: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(String(1000))
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    scope: Mapped["ProductScope"] = relationship(back_populates="products")
    listings: Mapped[list["ProductListing"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# Product Listings (specific URLs per source per product)
# ---------------------------------------------------------------------------


class ProductListing(Base):
    """
    One monitored URL for a specific product on a specific source.
    A product can have multiple listings (e.g. same product on idealo + amazon).
    """

    __tablename__ = "product_listings"
    __table_args__ = (UniqueConstraint("product_id", "source_id", "listing_url"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE")
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE")
    )
    listing_url: Mapped[str] = mapped_column(String(2000), nullable=False)
    listing_title: Mapped[str | None] = mapped_column(String(500))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_scraped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_available: Mapped[bool | None] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    product: Mapped["Product"] = relationship(back_populates="listings")
    source: Mapped["Source"] = relationship(back_populates="listings")
    price_history: Mapped[list["PriceHistory"]] = relationship(
        back_populates="listing", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# Price History (time-series)
# ---------------------------------------------------------------------------


class PriceHistory(Base):
    """
    One price record per scrape per listing. Append-only time-series.
    """

    __tablename__ = "price_history"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    listing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("product_listings.id", ondelete="CASCADE")
    )
    price_eur: Mapped[float | None] = mapped_column(Float)
    original_price_eur: Mapped[float | None] = mapped_column(Float)  # pre-discount
    in_stock: Mapped[bool | None] = mapped_column(Boolean)
    ships_to_germany: Mapped[bool | None] = mapped_column(Boolean)
    ships_from: Mapped[str | None] = mapped_column(String(200))
    delivery_days_min: Mapped[int | None] = mapped_column(Integer)
    delivery_days_max: Mapped[int | None] = mapped_column(Integer)
    screenshot_path: Mapped[str | None] = mapped_column(String(1000))
    raw_data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    listing: Mapped["ProductListing"] = relationship(back_populates="price_history")


# ---------------------------------------------------------------------------
# Pending Discoveries (new products awaiting user approval)
# ---------------------------------------------------------------------------


class PendingDiscovery(Base):
    """
    A product candidate found by the research agent.
    User must approve (→ added to products) or reject (→ archived).
    """

    __tablename__ = "pending_discoveries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    scope_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("product_scopes.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(200))
    model: Mapped[str | None] = mapped_column(String(200))
    specs: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    source_name: Mapped[str | None] = mapped_column(String(200))
    source_url: Mapped[str | None] = mapped_column(String(2000))
    price_eur: Mapped[float | None] = mapped_column(Float)
    in_stock: Mapped[bool | None] = mapped_column(Boolean)
    ships_to_germany: Mapped[bool | None] = mapped_column(Boolean)
    screenshot_path: Mapped[str | None] = mapped_column(String(1000))
    ai_reasoning: Mapped[str | None] = mapped_column(
        Text
    )  # why AI thinks this qualifies
    status: Mapped[str] = mapped_column(
        String(50), default="pending"
    )  # pending | approved | rejected
    found_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_notes: Mapped[str | None] = mapped_column(Text)
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_runs.id", ondelete="SET NULL")
    )

    # Relationships
    scope: Mapped["ProductScope"] = relationship(back_populates="pending_discoveries")
    agent_run: Mapped["AgentRun | None"] = relationship(back_populates="discoveries")


# ---------------------------------------------------------------------------
# Agent Runs (audit log)
# ---------------------------------------------------------------------------


class AgentRun(Base):
    """
    One record per pipeline execution (daily or manual).
    """

    __tablename__ = "agent_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    run_type: Mapped[str] = mapped_column(
        String(50), default="daily"
    )  # daily | manual
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        String(50), default="running"
    )  # running | completed | failed
    scopes_checked: Mapped[list[str]] = mapped_column(JSONB, default=list)
    products_checked: Mapped[int] = mapped_column(Integer, default=0)
    prices_updated: Mapped[int] = mapped_column(Integer, default=0)
    price_changes: Mapped[list[dict]] = mapped_column(
        JSONB, default=list
    )  # list of {product, old_price, new_price}
    discoveries_found: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    data_checks: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    tokens_used: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    log_text: Mapped[str | None] = mapped_column(Text)

    # Relationships
    discoveries: Mapped[list["PendingDiscovery"]] = relationship(
        back_populates="agent_run"
    )
    research_signals: Mapped[list["ResearchSignal"]] = relationship(
        back_populates="agent_run"
    )


# ---------------------------------------------------------------------------
# Research Intelligence (market signals and future watch items)
# ---------------------------------------------------------------------------


class ResearchSignal(Base):
    """
    A market intelligence signal discovered during research.
    Captures product launches, price trends, supply events, competitor intel, etc.

    signal_type values: product_launch | product_announcement | price_increase |
        price_decrease | availability_change | market_trend | supply_issue | competitor_intel

    significance values: low | medium | high | critical

    status values: new | watching | acted_on | expired
    """

    __tablename__ = "research_signals"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True
    )

    signal_type: Mapped[str] = mapped_column(String(50), nullable=False)
    significance: Mapped[str] = mapped_column(String(20), default="medium")

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)

    source_platform: Mapped[str | None] = mapped_column(String(100))
    source_url: Mapped[str | None] = mapped_column(String(2000))
    source_author: Mapped[str | None] = mapped_column(String(200))

    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    scope_slug: Mapped[str | None] = mapped_column(String(100))

    action_required: Mapped[bool] = mapped_column(Boolean, default=False)
    action_description: Mapped[str | None] = mapped_column(Text)
    follow_up_date: Mapped[str | None] = mapped_column(String(20))

    status: Mapped[str] = mapped_column(String(20), default="new")
    notes: Mapped[str | None] = mapped_column(Text)
    raw_data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    # Relationships
    watches: Mapped[list["ResearchWatch"]] = relationship(
        back_populates="signal", cascade="all, delete-orphan"
    )
    agent_run: Mapped["AgentRun | None"] = relationship(back_populates="research_signals")


class ResearchWatch(Base):
    """
    A specific item to monitor in future research runs, linked to a signal.

    watch_type values: check_price | check_availability | check_launch |
        search_x | search_news | check_eu_availability

    status values: pending | done | expired
    """

    __tablename__ = "research_watches"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    signal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("research_signals.id", ondelete="CASCADE")
    )

    watch_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    target_url: Mapped[str | None] = mapped_column(String(2000))
    search_query: Mapped[str | None] = mapped_column(String(500))

    check_by_date: Mapped[str | None] = mapped_column(String(20))
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    status: Mapped[str] = mapped_column(String(20), default="pending")
    result: Mapped[str | None] = mapped_column(Text)

    # Relationships
    signal: Mapped["ResearchSignal"] = relationship(back_populates="watches")
