"""Canonical Pydantic models for the Data Analytics metadata layer.

Mirror of the SQL schema in ``tables.py`` and the ORM wrappers in
``orm.py`` (NEU-1811 DA-P0). Spec:
``product-feature-roadmap/data-analytics/data-flow.md`` §4.8.

These are the boundary serialization models that flow between
connector-service, agent-platform, and the frontend. Per F4 in
``data-analytics/feature.md``:

  * connector-service uses ``DAConnection`` for tenant-level Connection
    lifecycle CRUD.
  * agent-platform uses ``WorkspaceMetadata`` and its sub-entities for
    metadata sync, T2S prompt rendering, and dashboard surfaces.

Per-service API request/response DTOs (e.g. credentials-masked responses,
input validators, computed-field extensions) live in their respective
service repos and project from these canonical types — they are NOT here.

Serialization conventions (per data-flow.md §4.8):

  * Same model for API, T2S prompt rendering, frontend.
  * ``model_dump_json()`` returns the canonical JSON shape.
  * Null / empty fields can be skipped at the call-site via
    ``exclude_none=True`` so the rendered payload is sparse-where-empty
    + rich-where-populated. The default keeps them so callers reading
    "what does the canonical shape look like" see every field.
  * ``model_validate(orm_instance)`` converts ORM rows to schemas via
    ``from_attributes=True`` on every model.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from neutrino_database.models.enums import (
    DAConnectionStatusEnum,
    DADescriptionScopeEnum,
    DADescriptionSourceEnum,
    DAJoinHintSourceEnum,
    DAJoinTypeEnum,
    DAMetricSourceEnum,
    DASourceTypeEnum,
    DATableTypeEnum,
)


# Shared base ----------------------------------------------------------------


class _DABase(BaseModel):
    """Common config for all DA canonical schemas.

    ``from_attributes=True`` enables conversion from SQLAlchemy ORM rows
    via ``Schema.model_validate(orm_row)``. ``use_enum_values=False`` keeps
    enums as enum instances so consumers can do enum-equality checks
    instead of string-equality on the wire format.
    """
    model_config = ConfigDict(
        from_attributes=True,
        use_enum_values=False,
        # Allow population by both field name and any aliases (used when
        # API DTOs in service repos extend / project these).
        populate_by_name=True,
    )


# Nested value types ---------------------------------------------------------


class ForeignKeyTarget(_DABase):
    """One element of ``Column.foreign_key_to`` — composite FKs supported
    by allowing multiple ForeignKeyTarget rows per column.
    """
    target_schema: str
    target_table: str
    target_column: str


class Synonym(_DABase):
    """Entity 7 (§4.8) — nested as a JSONB list inside ``Column.synonyms``.

    Stored as JSONB rather than its own table because churn is light and
    per-item HITL (source + accepted) is still expressible here.
    """
    term: str
    source: DAMetricSourceEnum  # admin_authored / ai_suggested / ai_accepted_by_admin
    accepted: bool = False


class StatisticalProfile(_DABase):
    """Phase-2 stats — shape stored as JSONB on ``Column.statistical_profile``.

    Compact on purpose: T2S rarely needs mean/median/stdev; analytics
    workflows do, but those are deferred to v2 per the "Deliberately
    NOT stored" table in §4.8.
    """
    null_proportion: Optional[float] = None
    unique_proportion: Optional[float] = None
    min_value: Optional[str] = None
    max_value: Optional[str] = None


# ---------------------------------------------------------------------------
# Tenant-level Connection (Step 1 of data-flow.md)
# ---------------------------------------------------------------------------


class DAConnection(_DABase):
    """The tenant-level DA Connection — the trust relationship + warehouse
    credentials. Connector-service owns lifecycle CRUD (F4).

    Note: ``credentials`` is included in the canonical model. Service-level
    API responses MUST project it out (or mask it). The canonical type is
    "what's stored"; service DTOs decide "what crosses the wire."
    """
    id: UUID
    tenant_id: UUID
    source_type: DASourceTypeEnum
    connection_name: str
    credentials: dict  # KMS-wrapped; opaque to consumers
    status: DAConnectionStatusEnum
    # Tenant-level schema allowlist (NEU-1811 DA-P1f). None = unrestricted;
    # list[str] = whitelist of allowed schema names.
    allowed_schemas: Optional[list[str]] = None
    created_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Workspace metadata layer (Entities 2–4, 7 in §4.8)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Tenant catalog (facts) — discovered by connector-service, shared across
# every workspace in the tenant.
# ---------------------------------------------------------------------------


class DACatalogColumn(_DABase):
    """Tenant-level column fact + compliance classification.

    DDL-derived facts (name, type, nullability, PK/FK, native_comment,
    ordinal) plus catalog-owned classification (is_pii / is_restricted).
    Per-workspace LLM context (descriptions, synonyms, sample values)
    lives on WorkspaceCurationDAColumn — facts up, opinions down.
    """
    id: UUID
    da_catalog_table_id: UUID

    # DDL-derived facts
    column_name: str
    data_type: str
    nullable: bool
    is_primary_key: bool = False
    is_foreign_key: bool = False
    foreign_key_to: Optional[list[ForeignKeyTarget]] = None
    native_comment: Optional[str] = None
    ordinal_position: int

    # Compliance classification — tenant-owned, no workspace override
    # for is_pii at all. is_restricted can only be upgraded via
    # WorkspaceCurationDAColumn.is_restricted_override.
    is_pii: bool = False
    is_restricted: bool = False

    last_synced_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class DACatalogTable(_DABase):
    """Tenant-level table fact within a catalog schema."""
    id: UUID
    da_catalog_schema_id: UUID

    table_name: str
    table_type: DATableTypeEnum
    native_comment: Optional[str] = None
    row_count: Optional[int] = None

    last_synced_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    # Children — assembled by the service layer when the consumer wants
    # the hierarchical view.
    columns: list[DACatalogColumn] = Field(default_factory=list)


class DACatalogSchema(_DABase):
    """Tenant-level schema fact within a Connection."""
    id: UUID
    da_connection_id: UUID

    schema_name: str
    schema_description: Optional[str] = None
    last_synced_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    tables: list[DACatalogTable] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Workspace curation overlays (opinions) — layered on top of the catalog.
# ---------------------------------------------------------------------------


class WorkspaceCurationDAColumn(_DABase):
    """Workspace overlay on a catalog column.

    Holds per-workspace LLM context — descriptions, synonyms, sample
    values, valid aggregations — plus the upgrade-only
    ``is_restricted_override``. No PII override field: PII is strictly
    catalog-owned for compliance consistency.
    """
    id: UUID
    workspace_id: UUID
    da_catalog_column_id: UUID

    # Per-workspace LLM context
    column_logical_name: Optional[str] = None
    admin_seed_description: Optional[str] = None
    ai_generated_description: Optional[str] = None
    synonyms: Optional[list[Synonym]] = None
    unit: Optional[str] = None
    format_hint: Optional[str] = None
    valid_aggregations: Optional[list[str]] = None

    # Phase-2 enrichment (admin opt-in)
    allow_sample_values: bool = False
    sample_values: Optional[list] = None
    cardinality_score: Optional[float] = None
    statistical_profile: Optional[StatisticalProfile] = None

    # Upgrade-only restricted override
    is_restricted_override: bool = False

    # Curation
    is_included: bool = False
    is_archived: bool = False
    last_enriched_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class WorkspaceCurationDATable(_DABase):
    """Workspace overlay on a catalog table."""
    id: UUID
    workspace_id: UUID
    da_catalog_table_id: UUID

    # Per-workspace opinion / context
    table_logical_name: Optional[str] = None
    admin_seed_description: Optional[str] = None
    ai_generated_description: Optional[str] = None

    # Curation
    is_included: bool = False
    is_archived: bool = False
    last_enriched_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    # Children — assembled by the service layer.
    columns: list[WorkspaceCurationDAColumn] = Field(default_factory=list)
    join_hints_from_here: list["JoinHint"] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Independent entities (5, 6, 8) — separate tables, separate lifecycles
# ---------------------------------------------------------------------------


class Metric(_DABase):
    """Entity 5 — workspace-scoped business metric. HITL via ``accepted``."""
    id: UUID
    workspace_id: UUID
    name: str
    description: Optional[str] = None
    sql_expression: str
    filters: Optional[str] = None
    applicable_tables: list[str] = Field(default_factory=list)
    valid_dimensions: Optional[list[str]] = None
    source: DAMetricSourceEnum
    accepted: bool = False
    created_by: Optional[UUID] = None
    updated_by: Optional[UUID] = None
    last_used_at: Optional[datetime] = None
    is_archived: bool = False
    created_at: datetime
    updated_at: datetime


class JoinHint(_DABase):
    """Entity 6 — workspace-scoped join hint between two curated tables."""
    id: UUID
    workspace_id: UUID
    left_table_id: UUID
    left_columns: list[str]
    right_table_id: UUID
    right_columns: list[str]
    join_type: DAJoinTypeEnum
    semantic_description: Optional[str] = None
    source: DAJoinHintSourceEnum
    accepted: bool = False
    created_by: Optional[UUID] = None
    is_archived: bool = False
    created_at: datetime


class DescriptionVersion(_DABase):
    """Entity 8 — append-only version row.

    Soft-FK: ``parent_id`` points at one of four parent tables depending
    on ``scope``. The service layer (agent-platform) enforces that the
    (scope, parent_id) pair is consistent — Postgres doesn't natively
    support discriminated FKs.
    """
    id: UUID
    scope: DADescriptionScopeEnum
    parent_id: UUID
    version_number: int
    source: DADescriptionSourceEnum
    content: str
    generated_at: datetime
    generated_by: Optional[UUID] = None
    # Open-ended dict — shape varies by source (AI-generated entries carry
    # DDL + comments + seed + samples + stats; admin-edited entries are
    # typically empty here; native_comment entries also empty).
    inputs_snapshot: Optional[dict] = None


# ---------------------------------------------------------------------------
# Root container — the canonical workspace metadata blob
# ---------------------------------------------------------------------------


class WorkspaceMetadata(_DABase):
    """Root container for a workspace's full DA metadata.

    Assembled by the service layer (agent-platform): joins
    ``da_catalog_schema / table / column`` (tenant facts) with
    ``workspace_curation_da_table / column`` (workspace opinions) for
    the workspace in question, plus its metrics and join hints. The
    same model is the "boundary serialization" contract from
    data-flow.md §4.8 — used for T2S prompt rendering, API responses,
    and frontend consumption.

    Note that ``DACatalogSchema`` is the top-level grouping because
    schemas are discovered facts; only the curated tables / columns
    nested under it carry workspace opinions.
    """
    workspace_id: UUID
    workspace_name: str
    last_synced_at: Optional[datetime] = None
    catalog_schemas: list[DACatalogSchema] = Field(default_factory=list)
    curated_tables: list[WorkspaceCurationDATable] = Field(default_factory=list)
    metrics: list[Metric] = Field(default_factory=list)


# Forward-reference resolution. WorkspaceCurationDATable holds a list of
# JoinHint, which is declared earlier in the file as a forward reference
# string; rebuild so the annotation resolves to the class object.
WorkspaceCurationDATable.model_rebuild()
