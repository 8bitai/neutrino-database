from enum import Enum


class ConnectionStatus(str, Enum):
    active = "active"
    error = "error"
    revoked = "revoked"

class KeyStatusEnum(str, Enum):
    CURRENT = "current"
    NEXT = "next"
    RETIRED = "retired"


class TenantStatusEnum(str, Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    REJECTED = "REJECTED"
    DELETED = "DELETED"
    PENDING_OPENFGA_SETUP = "PENDING_OPENFGA_SETUP"

class AllowedModuleEnum(str, Enum):
    ENTERPRISE_SEARCH = "Enterprise Search"
    DATA_ANALYTICS = "Data Analytics"
    WEB_SEARCH = "Web Search"
    DEEP_RESEARCH = "Deep Research"
    DASHBOARDS = "Dashboards"

class UserStatusEnum(str, Enum):
    INVITED = "INVITED"
    ACTIVE = "ACTIVE"
    DELETED = "DELETED"


class IdpProviderEnum(str, Enum):
    AZURE_AD = "AZURE_AD"
    GOOGLE_IDENTITY = "GOOGLE_IDENTITY"

class MemberSourceEnum(str, Enum):
    """How we discovered this member"""
    SSO_LOGIN = "SSO_LOGIN"              # User logged in via UI/Teams
    FILE_PERMISSIONS = "FILE_PERMISSIONS"  # From file permission sync


class FileProcessingStatusEnum(str, Enum):
    """Where a file is in its processing pipeline (X-DOC-1).

    The user-visible state machine that drives the FE status surface,
    Temporal workflow orchestration, and audit emission. See
    ``user-stories/connect-ingestion-refactor.md`` §6 for transitions
    and §7 for Temporal workflow architecture.

    Forward path:
        pending -> fetching -> fetched
                -> parsing -> chunking -> embedding
                -> indexing -> acl_replicated -> indexed
    Terminal:
        any -> failed (with error_code + error_message + retriable_at)
        any -> deleted (tombstone)
    Retry:
        failed -> fetching (new attempt_id)
    """

    PENDING = "pending"
    FETCHING = "fetching"
    FETCHED = "fetched"
    PARSING = "parsing"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    INDEXING = "indexing"
    ACL_REPLICATED = "acl_replicated"
    INDEXED = "indexed"
    FAILED = "failed"
    DELETED = "deleted"

class MessageRoleEnum(str, Enum):
    USER = "USER"
    ASSISTANT = "ASSISTANT"
    SYSTEM = "SYSTEM"

class WorkspaceStatusEnum(str, Enum):
    ACTIVE = "ACTIVE"
    DELETED = "DELETED"

class WorkspaceAccessStatusEnum(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class RouterModeEnum(str, Enum):
    AUTO = "AUTO"
    SEARCH_ONLY = "SEARCH_ONLY"
    ACTION_ONLY = "ACTION_ONLY"
    DA_ONLY = "DA_ONLY"


class PillarEnum(str, Enum):
    """
    The three product pillars a workspace can have enabled, in any
    combination. Replaces the conflated single-value RouterModeEnum
    as the source-of-truth for "what does this workspace do" — see
    `workspace.enabled_pillars` and the alembic migration that adds
    it. RouterModeEnum stays for now (agent-platform still reads it);
    the gateway writes both during a transition window.
    """
    ENTERPRISE_SEARCH = "ENTERPRISE_SEARCH"
    DATA_ANALYTICS = "DATA_ANALYTICS"
    WORKFLOW_EXECUTION = "WORKFLOW_EXECUTION"


class RetrievalStrategyEnum(str, Enum):
    SEMANTIC = "SEMANTIC"
    KEYWORD = "KEYWORD"
    HYBRID = "HYBRID"
    AGENTIC = "AGENTIC"

class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_INPUT = "waiting_input"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentMessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    OBSERVATION = "observation"


class ServiceType(str, Enum):
    """Supported AI service providers"""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    AZURE_OPENAI = "azure_openai"
    LANDINGAI = "landingai"


class ProviderCategory(str, Enum):
    """Categories of external service providers"""
    LLM = "llm"
    DOCUMENT_PARSER = "document_parser"
    EMBEDDING = "embedding"


class SpanType(str, Enum):
    """Types of observability spans recorded in trace_spans."""
    LLM = "llm"
    TOOL = "tool"
    AGENT = "agent"


class SpanStatus(str, Enum):
    """Outcome status of an observability span."""
    OK = "ok"
    ERROR = "error"


class ExcelDatasetStatus(str, Enum):
    """Lifecycle status of an uploaded Excel dataset."""
    READY = "ready"
    FAILED = "failed"
    DELETED = "deleted"


# ---------------------------------------------------------------------------
# Data Analytics pillar (NEU-1811 DA-P0).
#
# Eight enums backing the canonical metadata schema described in
# `product-feature-roadmap/data-analytics/data-flow.md` §4.8. Naming is
# DA-prefixed so they cannot collide with the legacy `ConnectionStatus`
# (which is the ES connector enum, shared with SharePoint/Drive auth).
# ---------------------------------------------------------------------------


class DAConnectionStatusEnum(str, Enum):
    """Lifecycle status of a tenant-level DA Connection.

    pending_auth — created but credentials not yet verified
    active       — credentials validated; ready for metadata sync + queries
    degraded     — last sync had recoverable errors (partial failure)
    error        — credentials invalid / persistent failure; admin attention
    disabled     — admin paused the connection
    """
    PENDING_AUTH = "pending_auth"
    ACTIVE = "active"
    DEGRADED = "degraded"
    ERROR = "error"
    DISABLED = "disabled"


class DASourceTypeEnum(str, Enum):
    """Warehouse source types supported by the DA pillar.

    v1 ships postgres + snowflake + bigquery; mysql + oracle queued. Mongo
    arrives later via a separate NoSqlBaseAdapter (per feature.md F5).
    """
    POSTGRES = "postgres"
    SNOWFLAKE = "snowflake"
    BIGQUERY = "bigquery"
    MYSQL = "mysql"
    ORACLE = "oracle"


class DATableTypeEnum(str, Enum):
    """Kind of relation surfaced by INFORMATION_SCHEMA.TABLES."""
    TABLE = "table"
    VIEW = "view"
    MATERIALIZED_VIEW = "materialized_view"


class DAMetricSourceEnum(str, Enum):
    """Where this Metric came from (HITL provenance).

    admin_authored        — Workspace Admin wrote it directly
    ai_suggested          — AI proposed; pending admin accept/reject
    ai_accepted_by_admin  — AI proposed and admin accepted unchanged
    """
    ADMIN_AUTHORED = "admin_authored"
    AI_SUGGESTED = "ai_suggested"
    AI_ACCEPTED_BY_ADMIN = "ai_accepted_by_admin"


class DAJoinHintSourceEnum(str, Enum):
    """Where this JoinHint came from (HITL provenance).

    inferred_from_fk — auto-derived from FK constraints during Phase 1 pull
    admin_authored / ai_suggested / ai_accepted_by_admin as above
    """
    ADMIN_AUTHORED = "admin_authored"
    INFERRED_FROM_FK = "inferred_from_fk"
    AI_SUGGESTED = "ai_suggested"
    AI_ACCEPTED_BY_ADMIN = "ai_accepted_by_admin"


class DAJoinTypeEnum(str, Enum):
    """SQL join semantics the hint describes."""
    INNER = "inner"
    LEFT = "left"
    RIGHT = "right"
    FULL = "full"


class DADescriptionScopeEnum(str, Enum):
    """What kind of row a description_version row belongs to.

    Soft-FK pattern: `description_version.parent_id` references one of
    four parent tables; `scope` discriminates. No DB-level FK because
    Postgres doesn't support discriminated FKs natively.
    """
    TABLE = "table"
    COLUMN = "column"
    METRIC = "metric"
    JOIN_HINT = "join_hint"


class DADescriptionSourceEnum(str, Enum):
    """Provenance of a description_version entry.

    native_comment  — copied from the source DDL during Phase 1
    ai_generated    — created by GovernedLLM (admin-triggered)
    ai_suggested    — AI proposed but not yet admin-accepted (HITL)
    admin_edited    — Workspace Admin wrote / overrode the description
    """
    NATIVE_COMMENT = "native_comment"
    AI_GENERATED = "ai_generated"
    AI_SUGGESTED = "ai_suggested"
    ADMIN_EDITED = "admin_edited"


# ---------------------------------------------------------------------------
# Dashboards (NEU-1811 DA-P3.1). Workspace-scoped authored surfaces
# built via the build chat. Draft/Published lifecycle + workspace /
# restricted / link-only visibility + per-widget data binding.
# ---------------------------------------------------------------------------


class DashboardStatusEnum(str, Enum):
    """Lifecycle status of a saved dashboard.

    draft     — work in progress, visible only to workspace admins
                in the Library's Drafts section.
    published — finalised, visible to every workspace member per
                the visibility flag.
    """
    DRAFT = "draft"
    PUBLISHED = "published"


class DashboardVisibilityEnum(str, Enum):
    """Audience scope for a published dashboard.

    workspace_members — every member of the workspace can view (default
                        for published dashboards).
    restricted        — explicit member / group allowlist via
                        dashboard_share rows. (v2; the table doesn't
                        ship in DA-P3.1 — TD-DASH-INTERNAL-SHARE-1.)
    link_only         — unlisted; only a link-token holder can view.
                        No workspace-member access by default.
    """
    WORKSPACE_MEMBERS = "workspace_members"
    RESTRICTED = "restricted"
    LINK_ONLY = "link_only"


class DashboardWidgetTypeEnum(str, Enum):
    """v1 widget catalog — what the canvas grid can render.

    Each maps 1:1 to a visualization renderer in
    components/visualizations on the FE side.
    """
    KPI_TILE = "kpi_tile"
    LINE_CHART = "line_chart"
    BAR_CHART = "bar_chart"
    STACKED_BAR = "stacked_bar"
    PIE_CHART = "pie_chart"
    DONUT_CHART = "donut_chart"
    TABLE = "table"
    TEXT = "text"


class ChatKindEnum(str, Enum):
    """What a chat thread is for (D6).

    ad_hoc          — the day-to-day Q&A chat surface. The default.
    dashboard_build — admin's build conversation with the dashboard
                      agent. One row per dashboard, set when the
                      dashboard is created. Drafts in the Library
                      are these chats.
    """
    AD_HOC = "ad_hoc"
    DASHBOARD_BUILD = "dashboard_build"


class DAAccessResourceTypeEnum(str, Enum):
    """Which DA catalog level a workspace_da_access_grant row applies
    to (X-DA-ACL-1). The grant + the resource_id together identify the
    exact node in the schema → table → column tree we're granting or
    denying access to."""
    SCHEMA = "schema"
    TABLE = "table"
    COLUMN = "column"


class DAAccessEffectEnum(str, Enum):
    """Two-state effect for a workspace_da_access_grant row
    (X-DA-ACL-1). 'Inherits parent' is the absence of any row at this
    level — it is never stored. Resolution rule applied by the
    service:

      * Walk the resource tree from leaf up (column → table → schema
        → workspace-member). Closest level with an explicit row
        wins.
      * At the same level, deny beats allow (column conflict can't
        happen given the UNIQUE constraint, but the rule still holds
        across levels: a child-allow can override a parent-deny).
      * Tenant Owner / Tenant Admin / Workspace Admin bypass entirely
        via the JWT projection.
      * M10 PII / Restricted catalog flags hard-block above all of
        this.
    """
    ALLOW = "allow"
    DENY = "deny"


# ---------------------------------------------------------------------------
# Unified integration hierarchy (WF-VS1) — the credential model shared across
# ES + DA + WF. See product-feature-roadmap/workflow-execution §5a, §9.
# ---------------------------------------------------------------------------


class IntegrationOwnerKindEnum(str, Enum):
    """Where an integration credential is owned. Three tiers — a tenant
    admin establishes corporate connections shared via enablement; a
    workspace admin can also establish a connection their workspace owns
    outright; any member can connect a personal credential. The CHECK
    constraint on ``integration`` ties this to the nullability of
    ``owner_user_id`` / ``workspace_id``:

      * ``tenant``    → owner_user_id IS NULL  AND workspace_id IS NULL
      * ``user``      → owner_user_id NOT NULL AND workspace_id NOT NULL
      * ``workspace`` → owner_user_id IS NULL  AND workspace_id NOT NULL
        (``workspace_id`` is the owning workspace)
    """
    TENANT = "tenant"
    USER = "user"
    WORKSPACE = "workspace"


class IntegrationIdentityKindEnum(str, Enum):
    """Who the destination SaaS sees when this credential is used.
    Derived from the provider catalog at create time, never
    client-supplied. Orthogonal to owner_kind."""
    USER = "user"
    APP = "app"
    SERVICE_ACCOUNT = "service_account"


class IntegrationAuthKindEnum(str, Enum):
    """How the credential authenticates. ``api_key`` / ``basic`` need no
    OAuth app registration (the member/tenant pastes a token);
    ``oauth2`` requires a platform or BYO app (Level-1 registration)."""
    OAUTH2 = "oauth2"
    API_KEY = "api_key"
    BASIC = "basic"
    CUSTOM = "custom"


class IntegrationStatusEnum(str, Enum):
    """Lifecycle of an integration credential."""
    ACTIVE = "active"
    DISABLED = "disabled"
    REVOKED = "revoked"
    EXPIRED = "expired"


class IntegrationEnablementStatusEnum(str, Enum):
    """Lifecycle of a per-workspace enablement of a tenant integration.
    Disabling pauses workspace use without revoking the underlying
    tenant credential."""
    ACTIVE = "active"
    DISABLED = "disabled"


class IntegrationGrantEffectEnum(str, Enum):
    """Two-state effect for an integration_member_grant row. Same
    deny-wins-anywhere semantics as DAAccessEffectEnum, scoped to
    integration capabilities. 'No row' = no explicit grant (default
    deny for members; admins bypass via JWT projection)."""
    ALLOW = "allow"
    DENY = "deny"


# ---------------------------------------------------------------------------
# Workflow Execution pillar (WF-VS2) — workflow definitions.
# ---------------------------------------------------------------------------


class WorkflowStatusEnum(str, Enum):
    """Lifecycle of a workflow definition.

    draft     — being built; not yet runnable on a schedule/trigger.
    active    — live; may be triggered / run.
    disabled  — paused without deletion (triggers won't fire).
    archived  — retired; retained for audit, hidden from the builder.
    """
    DRAFT = "draft"
    ACTIVE = "active"
    DISABLED = "disabled"
    ARCHIVED = "archived"
