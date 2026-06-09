"""[NEU-1816] CANON-DOC-1 — CanonicalDocument typed shape (shared package).

The single Python representation of a doc as it flows through the
ingestion pipeline. Every connector builds one of these; every pipeline
stage downstream of stage 4 consumes one. Agent-platform reads viewers
off it for retrieval-side ACL filtering.

Why this lives in the shared `neutrino_database` package: connector-
service, ES-Ingestion-Service, and agent-platform all depend on
neutrino-database. Putting the canonical shape here means the three
repos cannot drift — a change to the contract is a single commit.

The shape mirrors `product-feature-roadmap/enterprise-search/
unified-doc-parse-chunk.md` (§ CanonicalDocument). The schema landed by
Alembic migration ``c9e0a1b2d3f4`` is the JSON-equivalent of these
types stored in ``files``.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field


# Namespace for deterministic uuid5 doc_id generation. Fixed forever —
# changing this would break re-sync upsert semantics.
_DOC_NAMESPACE = UUID("00000000-0000-0000-0000-000000000001")


class SourceType(str, Enum):
    """Closed vocabulary of CanonicalDocument source kinds.

    Drives chunking regime (long-form regime A vs short-record regime
    B), citation card layout, default ranking weights (recency matters
    more for `message` and `issue` than for `file`), and chat-UI filter
    chips. New kinds require a schema migration AND a chunker-regime
    decision; do NOT add ad-hoc.
    """

    FILE = "file"               # SharePoint, Drive, OneDrive, Box, Dropbox, S3
    ISSUE = "issue"             # Jira, Linear, GitHub Issues
    PULL_REQUEST = "pull_request"   # GitHub PR, GitLab MR
    COMMIT = "commit"           # GitHub, GitLab
    PAGE = "page"               # Confluence, Notion, Google Sites
    RECORD = "record"           # Notion DB row, Salesforce, Airtable
    MESSAGE = "message"         # Slack, Teams, Discord
    EMAIL = "email"             # Outlook, Gmail
    EVENT = "event"             # Calendar
    COMMENT = "comment"         # sub-record of issue/page/PR
    ATTACHMENT = "attachment"   # file-shaped sub-record (parser dispatch path)
    TICKET = "ticket"           # Zendesk, Intercom, Freshdesk


class PrincipalKind(str, Enum):
    """Closed vocabulary of ACL principal kinds.

    Generalizes provider-specific kinds into the canonical four:
      * SharePoint user|group|sharepoint_group → user|group
      * Jira user|group|role → user|group (roles resolved to members)
      * Confluence user|group → user|group
    Plus two markers for cross-cutting "everyone in {workspace,tenant}"
    grants.
    """

    USER = "user"
    GROUP = "group"
    WORKSPACE_PUBLIC = "workspace_public"
    TENANT_PUBLIC = "tenant_public"


class Principal(BaseModel):
    """One entity that can read a CanonicalDocument.

    `external_id` carries the provider-native id (Jira accountId, AAD
    objectId, Confluence accountId, group external_id). The pipeline's
    stage 6.5 identity-mapping step resolves user-kind principals to
    Neutrino member.id via `user_mapping_service`; the resolved id is
    written to OpenFGA tuples and ES `acl_principals`. Principals that
    can't be resolved persist in ViewerSet.unmapped_external_ids for
    re-resolve on next sync.
    """

    model_config = ConfigDict(frozen=True)

    kind: PrincipalKind
    external_id: str = Field(
        ...,
        description=(
            "Provider-native id (Jira accountId / AAD object id / "
            "group key) — or the workspace_id for workspace_public."
        ),
    )
    email: str | None = Field(
        default=None,
        description=(
            "Used by the identity mapper for user-kind principals. "
            "PII — column-tagged at storage, hashed at retrieval-side."
        ),
    )
    display_name: str | None = Field(
        default=None,
        description="For citation rendering + audit logs.",
    )


class ViewerSet(BaseModel):
    """The resolved set of viewers for a CanonicalDocument.

    Source of truth for the doc's ACL. Drives both:
      * OpenFGA Store B `(doc, viewer, principal)` tuples (cross-cutting
        truth, used for compliance audits + re-resolves)
      * ES `acl_principals[]` denormalized keyword field (hot-path
        filter on every retrieval query)

    The pipeline's stage 7 writes both stores in lockstep — drift
    between them is the highest-severity bug class for this system.
    """

    principals: list[Principal] = Field(default_factory=list)
    is_public_in_workspace: bool = Field(
        default=False,
        description=(
            "True iff a workspace_public principal is in the set. "
            "Convenience flag so retrieval doesn't list-scan principals "
            "on every query."
        ),
    )
    extracted_at: datetime = Field(
        ...,
        description=(
            "When extract_viewers ran. Used to detect stale ACL "
            "(scheme change since this snapshot) on re-sync."
        ),
    )
    extractor_version: int = Field(
        default=1,
        description=(
            "Bumped on extractor-logic changes. Docs indexed with an "
            "older version are forced to re-resolve on next sync."
        ),
    )
    unmapped_external_ids: list[str] = Field(
        default_factory=list,
        description=(
            "Provider external_ids that couldn't map to Neutrino "
            "member.id (no email match / no SCIM provisioning yet). "
            "Re-resolved when the user signs up or is SCIM-provisioned."
        ),
    )


class CanonicalDocument(BaseModel):
    """The universal document shape — every connector emits one of these.

    The pipeline downstream of stage 4 is the SAME code regardless of
    whether the doc arrived from a file-source connector (SharePoint
    PDF, OneDrive DOCX) or a record-source connector (Jira issue,
    Confluence page, Slack message). The CanonicalDocument is what
    makes that uniformity possible.
    """

    # ─── Identity ──────────────────────────────────────────────────
    doc_id: UUID = Field(
        ...,
        description=(
            "Deterministic uuid5(NAMESPACE, '{tenant}:{provider}:"
            "{external_id}'). Re-syncs upsert; never duplicate. Build "
            "with the `build_doc_id` helper."
        ),
    )
    external_id: str = Field(
        ...,
        description="Provider's own id (file uuid, issue key, page id).",
    )
    integration_id: UUID
    tenant_id: UUID
    workspace_id: UUID

    # ─── Provenance ───────────────────────────────────────────────
    provider: str = Field(
        ...,
        description="'sharepoint' | 'jira' | 'confluence' | 'linear' | …",
    )
    source_type: SourceType
    source_url: str = Field(
        ...,
        description="Clickable link back to the source record.",
    )

    # ─── Display + cite ───────────────────────────────────────────
    title: str | None = Field(
        default=None,
        description=(
            "Nullable: Slack messages / GitHub commits / email "
            "snippets have no title — title_fallback covers citations."
        ),
    )
    title_fallback: str = Field(
        ...,
        description=(
            "Always populated — typically body[:80] — used when title "
            "is None for citation rendering."
        ),
    )
    container_id: str = Field(
        ...,
        description=(
            "Provider container — drive id / project key / space key / "
            "channel id / repo full_name."
        ),
    )
    container_name: str = Field(
        ...,
        description="Human-readable container name for citations.",
    )
    breadcrumb: list[str] = Field(
        default_factory=list,
        description="Full parent chain, e.g. ['Site','Library','Folder'].",
    )

    # ─── Content ──────────────────────────────────────────────────
    body: str = Field(..., description="The searchable text — usually markdown.")
    body_format: str = Field(default="markdown")
    language: str | None = Field(
        default=None,
        description="ISO 639-1 code; detected if not provided by source.",
    )

    # ─── Authoring ────────────────────────────────────────────────
    author_name: str | None = Field(default=None)
    author_email: str | None = Field(default=None, description="PII — column-tagged.")
    created_at: datetime
    last_modified: datetime

    # ─── Hierarchy ────────────────────────────────────────────────
    parent_doc_id: UUID | None = Field(
        default=None,
        description=(
            "Comment → issue, reply → thread root, attachment → page. "
            "ON DELETE CASCADE so removing parent removes children."
        ),
    )

    # ─── Access control (THE load-bearing field) ──────────────────
    viewers: ViewerSet = Field(
        ...,
        description=(
            "Resolved viewer set. Drives OpenFGA tuples AND ES "
            "acl_principals[]. Default-deny if principals is empty."
        ),
    )

    # ─── Filtering vs display split ───────────────────────────────
    facets: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "INDEXED as keyword on every ES chunk — for filter chips "
            "+ agent-driven facet filters. Provider names the keys."
        ),
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Display-only bag — surfaced in citation 'View details', "
            "never searched on. Stored in DB as `display_metadata` to "
            "avoid SQLAlchemy MetaData clash."
        ),
    )


def build_doc_id(tenant_id: UUID, provider: str, external_id: str) -> UUID:
    """Deterministic uuid5 from (tenant_id, provider, external_id).

    Same inputs → same UUID — guarantees re-syncs upsert, not duplicate.
    Different provider with same external_id → different doc_id (so a
    Jira and a Linear ticket numbered NEU-1816 don't collide).
    """
    return uuid5(_DOC_NAMESPACE, f"{tenant_id}:{provider}:{external_id}")
