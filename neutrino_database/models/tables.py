from sqlalchemy import (
    Table, Column, Integer, String, Text, TIMESTAMP, Index, Float, ForeignKey, BigInteger, Enum as PgEnum,
    UniqueConstraint, Numeric, DDL, event, CheckConstraint
)
from sqlalchemy.dialects.postgresql import JSONB, UUID, ARRAY, INET
from sqlalchemy.sql import func, text
from sqlalchemy import Boolean
from neutrino_database.models.base import metadata

from neutrino_database.models.enums import (
    AgentMessageRole,
    AllowedModuleEnum,
    ChatKindEnum,
    ConnectionStatus,
    DAAccessEffectEnum,
    DAAccessResourceTypeEnum,
    DAConnectionStatusEnum,
    DADescriptionScopeEnum,
    DADescriptionSourceEnum,
    DAJoinHintSourceEnum,
    DAJoinTypeEnum,
    DAMetricSourceEnum,
    DASourceTypeEnum,
    DATableTypeEnum,
    DashboardStatusEnum,
    DashboardVisibilityEnum,
    DashboardWidgetTypeEnum,
    ExcelDatasetStatus,
    FileProcessingStatusEnum,
    IdpProviderEnum,
    IntegrationAuthKindEnum,
    IntegrationEnablementStatusEnum,
    IntegrationGrantEffectEnum,
    IntegrationIdentityKindEnum,
    IntegrationOwnerKindEnum,
    IntegrationStatusEnum,
    WorkflowStatusEnum,
    KeyStatusEnum,
    MemberSourceEnum,
    MessageRoleEnum,
    PillarEnum,
    RetrievalStrategyEnum,
    RouterModeEnum,
    RunStatus,
    SpanStatus,
    SpanType,
    TenantStatusEnum,
    UserStatusEnum,
    WorkspaceAccessStatusEnum,
    WorkspaceStatusEnum,
)

import uuid


files = Table(
    "files",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("tenant_id", UUID(as_uuid=False), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
    Column("datasource_id", UUID(as_uuid=True), ForeignKey("datasources.id"), nullable=False),
    Column("workspace_id", UUID(as_uuid=False), ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),

    Column("external_file_info", JSONB, nullable=True, comment="Stores file_id and drive_id of external sources, e.g., SharePoint"),

    # File info
    Column("original_filename", String, nullable=False),
    Column("file_type", String(20), nullable=False),
    Column("storage_uri", Text, nullable=False),
    Column("file_size_bytes", BigInteger, nullable=False),
    Column("file_sha256", String(64), nullable=False),

    # Legacy free-form status (kept for backwards compatibility; deprecated
    # in favour of `processing_status` below — see TD-DOC-2).
    Column("status", String(50), nullable=False, server_default=text("'DOWNLOADED'")),

    # X-DOC-1 typed pipeline-state machine. Drives the FE status surface,
    # Temporal workflow orchestration, and audit emission. See
    # `user-stories/connect-ingestion-refactor.md` §6 for transitions.
    Column(
        "processing_status",
        PgEnum(
            FileProcessingStatusEnum,
            name="file_processing_status",
            values_callable=lambda enum: [e.value for e in enum],
        ),
        nullable=False,
        server_default=text("'pending'"),
    ),
    Column(
        "status_updated_at",
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
    Column("error_code", String(64), nullable=True),
    Column("error_message", Text, nullable=True),
    Column("error_retriable_at", TIMESTAMP(timezone=True), nullable=True),

    # Timestamps
    Column("created_at", TIMESTAMP(timezone=True), server_default=func.now(), nullable=False),
    Column("updated_at", TIMESTAMP(timezone=True), server_default=func.now(), nullable=False, onupdate=func.now()),

    Column("created_by", String, nullable=False),
    Column("is_deleted", Boolean, nullable=False, server_default=text("false")),

    Column("permission_mirroring_status", String(50), nullable=False, server_default=text("'NOT INITIATED'")),

    # Per-workspace + status filter is the dominant FE/admin query shape
    # ("show me failed files in this workspace").
    Index("ix_files_workspace_processing_status", "workspace_id", "processing_status"),
)


# ---------------------------------------------------------------------------
# X-DOC-1: ingestion's private retry / Temporal-state ledger.
#
# One row per file (lazy — only created when ingestion picks the file up).
# The canonical user-visible state stays on the `files` row; this side
# table holds retry counters, the current Temporal workflow id, and
# stage-specific payloads that would otherwise pollute the canonical row.
# Decision 5.9 in connect-ingestion-refactor.md.
# ---------------------------------------------------------------------------
file_processing_state = Table(
    "file_processing_state",
    metadata,
    Column(
        "file_id",
        UUID(as_uuid=True),
        ForeignKey("files.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "temporal_workflow_id",
        String(255),
        nullable=True,
        comment="Temporal workflow id for the in-flight ingestion run; "
                "shape: 'file:{uuid}'",
    ),
    Column(
        "attempt_id",
        Integer,
        nullable=False,
        server_default=text("1"),
        comment="Increments on each retry of the full pipeline. "
                "Used as part of the idempotency key for chunk / "
                "embedding writes.",
    ),
    Column(
        "last_activity",
        String(64),
        nullable=True,
        comment="Name of the most recently observed activity, e.g. "
                "'parse', 'chunk', 'embed', 'index', 'replicate_acl'.",
    ),
    Column(
        "retry_count",
        Integer,
        nullable=False,
        server_default=text("0"),
    ),
    Column("next_retry_at", TIMESTAMP(timezone=True), nullable=True),
    Column(
        "payload",
        JSONB,
        nullable=True,
        comment="Activity-specific opaque state. Ingestion writes here; "
                "documents-owner doesn't interpret.",
    ),
    Column(
        "created_at",
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
    Column(
        "updated_at",
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    ),

    Index(
        "ix_file_processing_state_due_retries",
        "next_retry_at",
        postgresql_where=text("next_retry_at IS NOT NULL"),
    ),
)


datasources = Table(
    "datasources",
    metadata,

    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("tenant_id", UUID(as_uuid=False), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
    Column("workspace_id", UUID(as_uuid=False), ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
    Column("name", String, nullable=False),
    Column("type", String, nullable=False),
    Column("config", JSONB, nullable=True),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", TIMESTAMP(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()),
)


ingestion_jobs = Table(
    "ingestion_jobs",
    metadata,

    # Identifiers
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("tenant_id", UUID(as_uuid=False), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
    Column("file_id", UUID(as_uuid=True), ForeignKey("files.id", ondelete="CASCADE"), nullable=False),
    Column("workspace_id", UUID(as_uuid=False), ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),

    # Status
    Column("overall_status", String(50), nullable=False, server_default=text("'READY_FOR_INGESTION'")),
    Column("progress_status", JSONB, nullable=True),
    Column("progress_percentage", Integer, nullable=False, server_default=text("0")),

    # Timestamps
    Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", TIMESTAMP(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()),

    Column("created_by", String, nullable=False),
    Column("is_deleted", Boolean, nullable=False, server_default=text("false")),

)

parsing = Table(
    "parsing",
    metadata,

    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("tenant_id", UUID(as_uuid=False),ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
    Column("file_id", UUID(as_uuid=True), ForeignKey("files.id", ondelete="CASCADE"), nullable=False),
    Column("workspace_id", UUID(as_uuid=False), ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),

    Column("page_no", Integer, nullable=False),
    Column("page_text", Text, nullable=False),
    Column("page_hash", Text, nullable=False),

    Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", TIMESTAMP(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()),

    Index("idx_parsing_file_page", "file_id", "page_no", unique=True)
)

chunk = Table(
    "chunk",
    metadata,

    # Identifiers
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("tenant_id", UUID(as_uuid=False), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
    Column("file_id", UUID(as_uuid=True), ForeignKey("files.id", ondelete="CASCADE"), nullable=False),
    Column("workspace_id", UUID(as_uuid=False), ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),

    Column("page_no", Integer, nullable=True, server_default=text("0")),
    Column("ord", Integer, nullable=True),
    Column("chunk_text", Text, nullable=False),
    Column("chunk_hash", Text, nullable=False),

    Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=func.now()),

    Index("idx_chunk_file_page_hash", "file_id", "page_no", "chunk_hash", unique=True)
)

embedding = Table(
    "embedding",
    metadata,

    # Identifiers
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("tenant_id", UUID(as_uuid=False), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
    Column("file_id", UUID(as_uuid=True), ForeignKey("files.id", ondelete="CASCADE"), nullable=False),
    Column("chunk_hash", String, nullable=False),
    Column("workspace_id", UUID(as_uuid=False), ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),

    # Dense vector - simple float array
    Column("dense_vector", ARRAY(Float), nullable=True),
    Column("dense_dim", Integer, nullable=False),

    # Sparse vector - JSONB with indices/values
    Column("sparse_vector", JSONB, nullable=True),
    Column("sparse_dim", Integer, nullable=True),

    # Metadata
    Column("model", String(100), nullable=True),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=func.now()),

    Index("idx_embedding_tenant_file_chunk_unique", "tenant_id", "file_id", "chunk_hash", unique=True)
)


index_sync = Table(
    "index_sync",
    metadata,
    Column("doc_id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=False), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
    Column("file_id", UUID(as_uuid=True), ForeignKey("files.id", ondelete="CASCADE"), nullable=False),
    Column("chunk_id", UUID(as_uuid=True), ForeignKey("chunk.id", ondelete="CASCADE"), nullable=False),
    Column("workspace_id", UUID(as_uuid=False), ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),

    Column("chunk_hash", Text, nullable=False),
    Column("ack_at", TIMESTAMP(timezone=True), nullable=True),
    Column("last_error", Text, nullable=True),
    Column("attempt_count", Integer, nullable=False, server_default=text("0"))
)


chunking_strategies = Table(
    "chunking_strategies",
    metadata,

    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("name", String, nullable=False),
    Column("description", Text, nullable=True),
    Column("config", JSONB, nullable=True),
    Column("is_active", Boolean, nullable=False, server_default=text("true")),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=func.now()),
)

strategies = Table(
    "strategies",
    metadata,

    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("tenant_id", UUID(as_uuid=False), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
    Column("name", String, nullable=False),
    Column("strategy_id", UUID(as_uuid=True), nullable=True),
    Column("workspace_id", UUID(as_uuid=False), ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
    # Foreign keys
    Column("file_id", UUID(as_uuid=True), ForeignKey("files.id", ondelete="CASCADE"), nullable=False),
    Column("chunking_strategy_id", UUID(as_uuid=True), ForeignKey("chunking_strategies.id", ondelete="CASCADE"), nullable=False),

    Column("description", Text, nullable=True),
    Column("custom_config", JSONB, nullable=True, server_default=text("'{}'::jsonb")),

    Column(
        "status",
        String,
        nullable=False,
        server_default=text("'draft'"),
    ),

    # Timestamps
    Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", TIMESTAMP(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()),

    # Audit fields
    Column("created_by", String, nullable=False),
    Column("updated_by", String, nullable=False),
    Column("is_deleted", Boolean, nullable=False, server_default=text("false")),
)


connector_types = Table(
    "connector_types",
    metadata,

    Column("id", String(100), primary_key=True),
    Column("display_name", String(255)),
    Column("category", String(100)),
    Column("auth_type", String(50)),
    # Note: config_schema removed - it's now stored in Connection model as it's tenant-specific
    Column("created_at", TIMESTAMP(timezone=True), server_default=func.now()),
    Column("updated_at", TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()),
)


connections = Table(
    "connections",
    metadata,

    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("tenant_id", UUID(as_uuid=True), nullable=False),
    Column("workspace_id", UUID(as_uuid=False), ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
    Column("connector_type_id", String(100), ForeignKey("connector_types.id"), nullable=False),
    Column("connection_name", String(255), nullable=False, server_default=text("'default'")),
    Column("status", PgEnum(ConnectionStatus), nullable=False, server_default=ConnectionStatus.active.name),
    Column("created_by", String(255)),
    Column("config_schema", Text),  # Workspace-specific configuration (e.g., SharePoint webUrl)
    Column("created_at", TIMESTAMP(timezone=True), server_default=func.now()),
    Column("updated_at", TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()),

    Index("ix_connection_workspace", "workspace_id"),
    Index(
        "ux_connection_tenant_workspace_type_name_active",
        "tenant_id",
        "workspace_id",
        "connector_type_id",
        "connection_name",
        unique=True,
        postgresql_where=text("status != 'revoked'"),
    ),
)


credentials = Table(
    "credentials",
    metadata,

    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("connection_id", UUID(as_uuid=True), ForeignKey("connections.id"), nullable=False),
    Column("resource", String(100), nullable=False),
    Column("access_token_encrypted", Text),
    Column("access_token_expires_at", TIMESTAMP(timezone=True)),
    Column("refresh_token_encrypted", Text),
    Column("scopes_or_resource", Text),
    Column("metadata", Text),  # Column name is "metadata" in DB
    Column("created_at", TIMESTAMP(timezone=True), server_default=func.now()),
    Column("updated_at", TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()),
)

lock_lease = Table(
    "mutex_locks",
    metadata,

    Column("name", Text, primary_key=True),
    Column("owner_id", Text, nullable=True),
    Column("lease_until", TIMESTAMP(timezone=True), nullable=True),
    Column("fencing_token", BigInteger, nullable=False, default=0),
)


rotation_mutex = Table(
    "rotation_mutex",
    metadata,

    Column("id", Boolean, primary_key=True, default=True),
    Column("held_by", Text, nullable=True),
    Column("held_since", TIMESTAMP(timezone=True), nullable=True),
)

signing_key = Table(
    "signing_keys",
    metadata,

    Column("kid", Text, primary_key=True),
    Column("public_pem", Text, nullable=False),
    Column("private_pem", Text, nullable=False),
    Column("status", PgEnum(KeyStatusEnum, name="key_status"), nullable=False),
    Column("not_before", TIMESTAMP(timezone=True), nullable=True),
    Column("not_after", TIMESTAMP(timezone=True), nullable=True),
    Column("created_at", TIMESTAMP(timezone=True), server_default=func.now(), nullable=False),
)

tenant_authz_store = Table(
    "tenant_authz_store",
    metadata,

    Column("id", UUID(as_uuid=False), primary_key=True, default=uuid.uuid4),
    Column("tenant_id", UUID(as_uuid=False), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False, unique=True),
    Column("store_id", String(255), nullable=False),
    Column("model_id", String(255), nullable=False),
    Column("created_at", TIMESTAMP(timezone=True), server_default=func.now(), nullable=False),
    Column("updated_at", TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False),
)

tenant = Table(
    "tenant",
    metadata,

    Column("id", UUID(as_uuid=False), primary_key=True, default=uuid.uuid4),
    Column("name", String(255), nullable=False),
    Column("org_external_id", String(200), nullable=False, unique=True),
    Column("status", PgEnum(TenantStatusEnum, name="tenant_status"), nullable=False, default=TenantStatusEnum.PENDING),
    Column("allowed_modules", JSONB, nullable=True, default=lambda: [module.value for module in AllowedModuleEnum]),
    Column("status_updated_at", TIMESTAMP(timezone=True), nullable=True),
    Column("status_updated_by", UUID(as_uuid=False), nullable=True),
    Column("status_reason", Text, nullable=True),
    Column("tenant_owner", UUID(as_uuid=False), ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
    # First-class signal of "this tenant has finished initial onboarding."
    # Stamped atomically by POST /api/v1/onboarding/complete; replaces the
    # !workspace_id proxy used by the FE post-auth callback to decide
    # /welcome vs /chat.
    Column("onboarding_completed_at", TIMESTAMP(timezone=True), nullable=True),
    # Per-tenant cap on active workspaces (NEU-1805 § 1d). Soft-deleted
    # workspaces don't count; the retention runner cleans them up at
    # 30 days. Default 50 covers real teams; enterprise raises it via a
    # one-row UPDATE rather than a code change.
    Column("max_workspaces", Integer, nullable=False, server_default=text("50")),
    # Owner-controlled domain allowlist for invitations (NEU-X4).
    # Empty array = no restriction (anyone can be invited). Non-empty
    # = invitations rejected unless the invitee's email domain is in
    # the list. Owner edits this via /tenants/{id}/settings.
    # Replaces the previous hardcoded "must match owner email domain"
    # check that broke for orgs with multiple legitimate domains
    # (IBM: ibm.com, ibm.co.in, ibm.co.uk, …).
    Column(
        "allowed_invitation_domains",
        ARRAY(Text),
        nullable=False,
        server_default=text("'{}'::text[]"),
    ),
    Column("created_at", TIMESTAMP(timezone=True), server_default=func.now(), nullable=False),
    Column("updated_at", TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False),
    Column("deleted_at", TIMESTAMP(timezone=True), nullable=True),

    Index("ix_tenant_status", "status"),
    Index("ix_tenant_created_at", "created_at"),
)

user = Table(
    "user",
    metadata,

    Column("id", UUID(as_uuid=False), primary_key=True, default=uuid.uuid4),
    Column("tenant_id", UUID(as_uuid=False), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
    Column("email", String(320), nullable=False, comment="pii:email"),
    Column("display_name", String(255), nullable=True, comment="pii:name"),
    Column("status", PgEnum(UserStatusEnum, name="user_status"), nullable=False, default=UserStatusEnum.ACTIVE),
    Column("first_login_at", TIMESTAMP(timezone=True), nullable=True),
    Column("last_login_at", TIMESTAMP(timezone=True), nullable=True),
    Column("created_at", TIMESTAMP(timezone=True), server_default=func.now(), nullable=False),
    Column("updated_at", TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False),
    Column("deleted_at", TIMESTAMP(timezone=True), nullable=True),
    Column("default_workspace_id", UUID(as_uuid=False), ForeignKey("workspace.id", ondelete="SET NULL"), nullable=True),

    # Local auth columns — nullable so SSO-only users are unaffected
    Column("username", String(100), nullable=True, comment="pii:name"),
    Column("password_hash", Text, nullable=True),
    Column("must_change_password", Boolean, nullable=False, server_default="false"),
    Column("password_changed_at", TIMESTAMP(timezone=True), nullable=True),

    # NEU-X8 — Authorization-state freshness marker. Touched whenever any
    # claim affecting this user's principal changes (promote/demote
    # tenant admin, promote/demote workspace admin, ownership transfer
    # accept on either side). The auth middleware compares the JWT's
    # `iat` against this column on each request; if `permissions_changed_at`
    # is newer, the JWT is force-renewed regardless of the normal
    # renewal-window threshold. Closes the "promoted-but-FE-still-shows-
    # non-admin until sign-out + sign-in" UX gap. Defaults to created_at
    # so existing rows behave like "no change since issuance" for
    # back-compat.
    Column("permissions_changed_at", TIMESTAMP(timezone=True), nullable=True),

    UniqueConstraint("tenant_id", "email", name="ux_user_tenant_email"),
    UniqueConstraint("tenant_id", "username", name="ux_user_tenant_username"),  # NULLs excluded from uniqueness — multiple SSO-only users per tenant are valid
    Index("ix_user_tenant_status", "tenant_id", "status"),
    Index("ix_user_last_login_at", "last_login_at"),
    Index("ix_user_tenant_username_lower", "tenant_id", func.lower(Column("username", String(100))), unique=True, postgresql_where=text("username IS NOT NULL")),
    Index("ix_user_email_lower_active", func.lower(Column("email", String(320))), postgresql_where=text("deleted_at IS NULL")),
    Index("ix_user_username_lower_active", func.lower(Column("username", String(100))), postgresql_where=text("deleted_at IS NULL AND username IS NOT NULL")),
)

tenant_identity = Table(
    "tenant_identity",
    metadata,

    Column("id", UUID(as_uuid=False), primary_key=True, default=uuid.uuid4),
    Column("tenant_id", UUID(as_uuid=False), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
    Column("provider", PgEnum(IdpProviderEnum, name="idp_provider"), nullable=False, default=IdpProviderEnum.AZURE_AD),
    Column("provider_org_id", String(200), nullable=False),
    Column("created_at", TIMESTAMP(timezone=True), server_default=func.now(), nullable=False),

    UniqueConstraint("provider", "provider_org_id", name="ux_tenant_identity_provider_org"),
)

sso_identity = Table(
    "sso_identity",
    metadata,

    Column("id", UUID(as_uuid=False), primary_key=True, default=uuid.uuid4),
    Column("user_id", UUID(as_uuid=False), ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
    Column("provider", PgEnum(IdpProviderEnum, name="idp_provider"), nullable=False, default=IdpProviderEnum.AZURE_AD),
    Column("provider_user_id", String(200), nullable=False),
    Column("provider_org_id", String(200), nullable=False),
    Column("last_login_at", TIMESTAMP(timezone=True), nullable=True),
    Column("raw_profile", JSONB, nullable=True),
    Column("created_at", TIMESTAMP(timezone=True), server_default=func.now(), nullable=False),
    Column("updated_at", TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False),

    UniqueConstraint("provider", "provider_user_id", name="ux_sso_identity_provider_user"),
    Index("ix_sso_identity_provider_org", "provider", "provider_org_id"),
    Index("ix_sso_identity_user_id", "user_id"),
)

member = Table(
    "member",
    metadata,

    Column("id", UUID(as_uuid=False), primary_key=True, default=uuid.uuid4),
    Column("user_id", UUID(as_uuid=False), ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
    Column("email", String(255), nullable=True),
    Column("name", String(255), nullable=True),
    Column("provider", PgEnum(IdpProviderEnum, name="idp_provider"), nullable=False, default=IdpProviderEnum.AZURE_AD),
    Column("provider_user_id", String(200), nullable=False),
    Column("provider_org_id", String(200), nullable=False),
    Column("source", PgEnum(MemberSourceEnum, name="member_source"), nullable=False, default=MemberSourceEnum.SSO_LOGIN),
    Column("created_at", TIMESTAMP(timezone=True), server_default=func.now(), nullable=False),
    Column("updated_at", TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False),

    UniqueConstraint("provider", "provider_user_id", name="ux_member_provider_user"),
    Index("ix_member_provider_org", "provider", "provider_org_id"),
    Index("ix_member_user_id", "user_id"),
    Index("ix_member_source", "source"),
)

role = Table(
    "role",
    metadata,

    Column("id", UUID(as_uuid=False), primary_key=True, default=uuid.uuid4),
    Column("tenant_id", UUID(as_uuid=False), ForeignKey("tenant.id"), nullable=False),
    Column("key", String(120), nullable=False),
    Column("name", String(255), nullable=False),
    Column("description", Text, nullable=True),

    UniqueConstraint("tenant_id", "key", name="ux_role_tenant_key"),
    Index("ix_role_tenant_name", "tenant_id", "name"),
)

app_permission = Table(
    "app_permission",
    metadata,

    Column("id", UUID(as_uuid=False), primary_key=True, default=uuid.uuid4),
    Column("key", String(120), nullable=False, unique=True),
    Column("name", String(255), nullable=False),
    Column("description", Text, nullable=True),
)

user_invitation = Table(
    "user_invitation",
    metadata,

    Column("id", UUID(as_uuid=False), primary_key=True, default=uuid.uuid4),
    Column("tenant_id", UUID(as_uuid=False), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
    Column("inviter", UUID(as_uuid=False), ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
    Column("email", String(320), nullable=False),
    Column("expires_at", TIMESTAMP(timezone=True), nullable=False),
    Column("accepted_at", TIMESTAMP(timezone=True), nullable=True),
    Column("deleted_at", TIMESTAMP(timezone=True), nullable=True),
    Column("created_at", TIMESTAMP(timezone=True), server_default=func.now(), nullable=False),

    Index("ix_user_invitation_tenant_email", "tenant_id", "email"),
    Index("ix_user_invitation_expires_at", "expires_at"),
    Index("ix_user_invitation_tenant_email_pending", "tenant_id", "email", postgresql_where=text("accepted_at IS NULL AND deleted_at IS NULL")),
)

chat = Table(
    "chat",
    metadata,

    Column("id", UUID(as_uuid=False), primary_key=True, default=uuid.uuid4),
    Column("tenant_id", UUID(as_uuid=False), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
    # Workspace this chat thread belongs to (X-CHAT-WS-1). NOT NULL —
    # every chat lives inside exactly one workspace. CASCADE so that
    # deleting a workspace removes its chats (mirrors
    # ``dashboard.workspace_id`` which is also CASCADE). Without this
    # column the per-workspace list query has nothing to ground its
    # authorization on, so a Tenant Admin in two workspaces sees the
    # same threads in both — see X-CHAT-WS-1 for context.
    Column(
        "workspace_id",
        UUID(as_uuid=False),
        ForeignKey("workspace.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("created_by", UUID(as_uuid=False), ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
    Column("title", String(255), nullable=True),
    Column("incognito", Boolean, nullable=False, server_default=text("false")),
    Column("pinned", Boolean, nullable=False, server_default=text("false")),
    # D6 — what this chat is for. ``ad_hoc`` (default) is the day-to-
    # day Q&A chat surface. ``dashboard_build`` flags this row as the
    # build conversation behind one Dashboard (linked via the
    # ``dashboard.build_chat_id`` FK back-pointer). Drafts in the
    # Library are these chats.
    Column(
        "kind",
        PgEnum(
            ChatKindEnum,
            name="chat_kind",
            values_callable=lambda enum: [e.value for e in enum],
        ),
        nullable=False,
        server_default=text("'ad_hoc'"),
    ),
    # Back-pointer to the dashboard this chat is building. NULL for
    # ad_hoc chats. CASCADE on the dashboard side so deleting a
    # dashboard also wipes its build chat — drafts and dashboards have
    # a 1:1 lifecycle.
    Column(
        "dashboard_id",
        UUID(as_uuid=False),
        ForeignKey("dashboard.id", ondelete="CASCADE"),
        nullable=True,
    ),
    Column("created_at", TIMESTAMP(timezone=True), server_default=func.now(), nullable=False),
    Column("updated_at", TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False),
    Column("deleted_at", TIMESTAMP(timezone=True), nullable=True),

    Index("ix_chat_tenant_incognito", "tenant_id", "incognito"),
    Index("ix_chat_tenant_non_incognito", "tenant_id", postgresql_where=text("incognito = false")),
    Index("ix_chat_tenant_updated_at", "tenant_id", "updated_at"),
    # Per-user per-workspace list index (X-CHAT-WS-1). Keys exactly
    # the FE's list query:
    #   WHERE workspace_id = :ws AND created_by = :user
    #         AND deleted_at IS NULL
    #   ORDER BY updated_at DESC
    # Partial on ``deleted_at IS NULL`` so soft-deleted rows don't
    # bloat the index.
    Index(
        "ix_chat_workspace_created_by_updated_at",
        "workspace_id",
        "created_by",
        text("updated_at DESC"),
        postgresql_where=text("deleted_at IS NULL"),
    ),
)

message = Table(
    "message",
    metadata,

    Column("id", UUID(as_uuid=False), primary_key=True, default=uuid.uuid4),
    Column("tenant_id", UUID(as_uuid=False), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
    Column("chat_id", UUID(as_uuid=False), ForeignKey("chat.id", ondelete="CASCADE"), nullable=False),
    Column("user_id", UUID(as_uuid=False), ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
    Column("role", PgEnum(MessageRoleEnum, name="message_role"), nullable=False, default=MessageRoleEnum.USER),
    Column("content", Text, nullable=False),
    Column("created_at", TIMESTAMP(timezone=True), server_default=func.now(), nullable=False),
    Column("updated_at", TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False),
    Column("deleted_at", TIMESTAMP(timezone=True), nullable=True),

    Index("ix_message_chat_created_at", "chat_id", "created_at"),
    Index("ix_message_tenant_chat", "tenant_id", "chat_id"),
    Index("ix_message_user_id", "user_id"),
)


workspace = Table(
    "workspace",
    metadata,

    Column("id", UUID(as_uuid=False), primary_key=True, default=uuid.uuid4),
    Column("tenant_id", UUID(as_uuid=False), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
    Column("name", String(255), nullable=False),
    Column("description", Text, nullable=True),
    Column("status", PgEnum(WorkspaceStatusEnum, name="workspace_status"), nullable=False, server_default=WorkspaceStatusEnum.ACTIVE.name),
    # Multi-select pillar enablement. Replaces the single-value
    # orchestrator_config.router_mode as source-of-truth for "what
    # this workspace does." During the transition window the gateway
    # writes both; agent-platform still reads router_mode. A later
    # cleanup migration drops router_mode once readers catch up.
    Column(
        "enabled_pillars",
        ARRAY(PgEnum(PillarEnum, name="pillar")),
        nullable=False,
        server_default=text("'{}'::pillar[]"),
    ),
    Column("created_by", UUID(as_uuid=False), ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
    Column("created_at", TIMESTAMP(timezone=True), server_default=func.now(), nullable=False),
    Column("updated_at", TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False),
    Column("deleted_at", TIMESTAMP(timezone=True), nullable=True),
    # Soft-delete-with-grace metadata (NEU-1805 § 1c). The retention
    # runner uses deletion_scheduled_for to decide when to physically
    # remove the row; the value is stored explicitly (rather than
    # computed from deleted_at + grace period) so a future change to
    # the grace constant doesn't silently shift existing pending
    # deletions.
    Column("deletion_scheduled_for", TIMESTAMP(timezone=True), nullable=True),
    # Audit-correlatable; FK SET NULL so a user can be anonymized
    # (GDPR Art. 17) without breaking workspace deletion history.
    Column(
        "deletion_initiated_by",
        UUID(as_uuid=False),
        ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
    ),

    # Partial unique index: name uniqueness applies only to active
    # workspaces. Soft-deleted workspaces don't block a new workspace
    # with the same name during the 30-day grace period — without
    # this, deleting "Engineering" would make the name unavailable
    # for 30 days even though the deletion may yet be reversed.
    Index(
        "ux_workspace_tenant_name_active",
        "tenant_id",
        "name",
        unique=True,
        postgresql_where=text("deleted_at IS NULL"),
    ),
    Index("ix_workspace_tenant", "tenant_id"),
    Index("ix_workspace_tenant_status", "tenant_id", "status"),
    Index(
        "ix_workspace_pending_deletion",
        "deletion_scheduled_for",
        postgresql_where=text("deleted_at IS NOT NULL AND deletion_scheduled_for IS NOT NULL"),
    ),
)

workspace_member = Table(
    "workspace_member",
    metadata,

    Column("id", UUID(as_uuid=False), primary_key=True, default=uuid.uuid4),
    Column("workspace_id", UUID(as_uuid=False), ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
    Column("user_id", UUID(as_uuid=False), ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
    Column("is_workspace_admin", Boolean, nullable=False, server_default=text("false")),
    Column("created_at", TIMESTAMP(timezone=True), server_default=func.now(), nullable=False),
    Column("updated_at", TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False),

    # X-WORKSPACE-MEMBER-UX-1 P3 — first-visit timestamp drives the
    # cinematic-welcome trigger. NULL = hasn't visited yet (cinematic
    # plays on next landing). Per-membership-row rather than
    # per-user so a member removed and re-added gets a fresh welcome.
    Column("first_visited_at", TIMESTAMP(timezone=True), nullable=True),

    UniqueConstraint("workspace_id", "user_id", name="ux_workspace_member_workspace_user"),
    Index("ix_workspace_member_workspace", "workspace_id"),
    Index("ix_workspace_member_user", "user_id"),
    Index("ix_workspace_member_workspace_admin", "workspace_id", "is_workspace_admin"),
)

workspace_access_request = Table(
    "workspace_access_request",
    metadata,

    Column("id", UUID(as_uuid=False), primary_key=True, default=uuid.uuid4),
    Column("workspace_id", UUID(as_uuid=False), ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
    Column("user_id", UUID(as_uuid=False), ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
    Column("status", PgEnum(WorkspaceAccessStatusEnum, name="workspace_access_status"), nullable=False, server_default=WorkspaceAccessStatusEnum.PENDING.name),
    Column("requested_at", TIMESTAMP(timezone=True), server_default=func.now(), nullable=False),
    Column("reviewed_by", UUID(as_uuid=False), ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
    Column("reviewed_at", TIMESTAMP(timezone=True), nullable=True),
    Column("review_note", Text, nullable=True),

    Index("ix_workspace_access_request_workspace_status", "workspace_id", "status"),
    Index("ix_workspace_access_request_user_status", "user_id", "status"),
)

workspace_invitation = Table(
    "workspace_invitation",
    metadata,

    Column("id", UUID(as_uuid=False), primary_key=True, default=uuid.uuid4),
    Column("workspace_id", UUID(as_uuid=False), ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
    Column("inviter", UUID(as_uuid=False), ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
    Column("email", String(320), nullable=False, comment="pii:email"),
    Column("is_workspace_admin", Boolean, nullable=False, server_default=text("false")),
    # Optional personal note from the inviter, included verbatim in the
    # invitation email and persisted so resend-invitation flows reuse the
    # same wording. Length is capped at the gateway boundary (Pydantic),
    # not at the column — the DB stays permissive. Tagged pii:freetext
    # because it may contain identifying info (names, role descriptions).
    Column("personal_message", Text, nullable=True, comment="pii:freetext"),
    Column("expires_at", TIMESTAMP(timezone=True), nullable=False),
    Column("accepted_at", TIMESTAMP(timezone=True), nullable=True),
    Column("deleted_at", TIMESTAMP(timezone=True), nullable=True),
    Column("created_at", TIMESTAMP(timezone=True), server_default=func.now(), nullable=False),

    Index("ix_workspace_invitation_workspace_email", "workspace_id", "email"),
    Index("ix_workspace_invitation_email", "email"),
    Index("ix_workspace_invitation_expires_at", "expires_at"),
    Index("ix_workspace_invitation_email_pending", "email", postgresql_where=text("accepted_at IS NULL AND deleted_at IS NULL")),
)

orchestrator_config = Table(
    "orchestrator_config",
    metadata,

    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("workspace_id", UUID(as_uuid=True), ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False, unique=True),

    Column("router_mode", PgEnum(RouterModeEnum, name="router_mode"), nullable=False, server_default=RouterModeEnum.AUTO.name),
    Column("router_classification_prompt", Text, nullable=True),
    Column("response_synthesis_prompt", Text, nullable=True),

    # Retrieval strategy configuration
    Column("retrieval_strategy", PgEnum(RetrievalStrategyEnum, name="retrieval_strategy"), nullable=False, server_default=RetrievalStrategyEnum.HYBRID.name),
    Column("retrieval_config", JSONB, nullable=False, server_default=text("'{\"top_k\": 3, \"semantic_weight\": 0.3}'::jsonb")),

    Column("created_at", TIMESTAMP(timezone=True), server_default=func.now(), nullable=False),
    Column("updated_at", TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False),

    Index("ix_orchestrator_config_workspace", "workspace_id"),
)

runs = Table(
    "runs",
    metadata,

    Column("id", String(26), primary_key=True),  # ULID
    Column("message_id", UUID(as_uuid=False), ForeignKey("message.id", ondelete="CASCADE"), nullable=False),
    Column("session_id", UUID(as_uuid=False), ForeignKey("chat.id", ondelete="CASCADE"), nullable=True),
    Column("tenant_id", UUID(as_uuid=False), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
    Column("workspace_id", UUID(as_uuid=False), ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
    Column("user_id", UUID(as_uuid=False), ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
    Column("status", PgEnum(RunStatus, name="run_status",values_callable=lambda x: [e.value for e in x]), nullable=False, server_default=text("'pending'")),
    Column("input_message", Text, nullable=False),
    Column("final_answer", Text, nullable=True),
    Column("sources", JSONB, nullable=True),  # Citation sources from enterprise_search

    # Workflow execution tracking
    Column("flow_run_id", String(50), nullable=True),  # Activepieces flow run ID for terminate support

    # HITL (Human-in-the-Loop) support
    Column("waiting_instance_id", String(50), nullable=True),  # Which agent instance is waiting
    Column("input_request", JSONB, nullable=True),  # {"question": "...", "form_schema": {...}}

    Column("created_at", TIMESTAMP(timezone=True), server_default=func.now(), nullable=False),
    Column("updated_at", TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False),

    Index("ix_runs_message_id", "message_id"),
    Index("ix_runs_session_id", "session_id"),
    Index("ix_runs_tenant_id", "tenant_id"),
    Index("ix_runs_workspace_id", "workspace_id"),
    Index("ix_runs_user_id", "user_id"),
    Index("ix_runs_status", "status"),
)



react_conversations = Table(
    "react_conversations",
    metadata,

    Column("id", String(26), primary_key=True),  # ULID
    Column("run_id", String(26), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False),
    Column("instance_id", String(50), nullable=True),  # Sub-agent invocation ID (prefix + ULID)
    Column("delegation_level", Integer, nullable=False, server_default=text("0")),  # 0=main, 1=sub-agent
    Column("agent_name", String(100), nullable=False),
    Column("role", PgEnum(AgentMessageRole, name="agent_message_role",values_callable=lambda x: [e.value for e in x]), nullable=False),
    Column("content", Text, nullable=False),
    Column("tool_name", String(100), nullable=True),
    Column("tool_params", JSONB, nullable=True),
    Column("created_at", TIMESTAMP(timezone=True), server_default=func.now(), nullable=False),

    Index("ix_react_conversations_run_id", "run_id"),
    Index("ix_react_conversations_instance_id", "instance_id"),
)

run_events = Table(
    "run_events",
    metadata,

    Column("id", String(26), primary_key=True),  # ULID
    Column("run_id", String(26), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False),
    Column("sequence", Integer, nullable=False, server_default=text("0")),  # Order within run for SSE resume
    Column("event_type", String(50), nullable=False),  # thinking, tool_call, observation, answer, error
    Column("agent_name", String(100), nullable=True),
    Column("instance_id", String(50), nullable=True),  # Sub-agent invocation ID (prefix + ULID)
    Column("data", JSONB, nullable=True),
    Column("created_at", TIMESTAMP(timezone=True), server_default=func.now(), nullable=False),

    Index("ix_run_events_run_id", "run_id"),
    Index("ix_run_events_sequence", "run_id", "sequence"),
)


trace_spans = Table(
    "trace_spans",
    metadata,

    Column("id", String(26), primary_key=True),  # ULID
    Column("run_id", String(26), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False),
    Column("parent_span_id", String(26), ForeignKey("trace_spans.id", ondelete="CASCADE"), nullable=True),
    Column("sequence", Integer, nullable=False, server_default=text("0")),

    Column("span_type", PgEnum(SpanType, name="span_type", values_callable=lambda x: [e.value for e in x]), nullable=False),
    Column("name", String(200), nullable=False),
    Column("agent_name", String(100), nullable=True),
    Column("status", PgEnum(SpanStatus, name="span_status", values_callable=lambda x: [e.value for e in x]), nullable=False),

    Column("started_at", TIMESTAMP(timezone=True), nullable=False),
    Column("ended_at", TIMESTAMP(timezone=True), nullable=False),
    Column("latency_ms", Integer, nullable=False),

    Column("attributes", JSONB, nullable=True),

    Column("created_at", TIMESTAMP(timezone=True), server_default=func.now(), nullable=False),

    Index("ix_trace_spans_run_id", "run_id"),
    Index("ix_trace_spans_run_type", "run_id", "span_type"),
    Index("ix_trace_spans_run_sequence", "run_id", "sequence"),
    Index("ix_trace_spans_parent", "parent_span_id"),
)


excel_datasets = Table(
    "excel_datasets",
    metadata,

    Column("id", String(26), primary_key=True),  # ULID
    Column("workspace_id", UUID(as_uuid=False), ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
    Column("tenant_id", UUID(as_uuid=False), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
    Column("uploaded_by", UUID(as_uuid=False), ForeignKey("user.id", ondelete="SET NULL"), nullable=True),

    Column("original_filename", String(500), nullable=False),
    Column("schema_name", String(200), nullable=False, unique=True),
    Column("minio_path", String(1000), nullable=False),

    Column("status", PgEnum(ExcelDatasetStatus, name="excel_dataset_status", values_callable=lambda x: [e.value for e in x]), nullable=False),
    Column("table_metadata", JSONB, nullable=True),
    Column("file_size_bytes", BigInteger, nullable=False),
    Column("error_details", Text, nullable=True),

    Column("created_at", TIMESTAMP(timezone=True), server_default=func.now(), nullable=False),
    Column("updated_at", TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False),

    Index("ix_excel_datasets_workspace", "workspace_id"),
    Index("ix_excel_datasets_tenant", "tenant_id"),
)


log_connectors = Table(
    "log_connectors",
    metadata,

    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("tenant_id", UUID(as_uuid=False), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
    Column("connector_name", String(255), nullable=False),
    Column("connector_type", String(50), nullable=False, server_default=text("'elasticsearch'")),
    Column("config", JSONB, nullable=False),
    Column("status", String(50), nullable=False, server_default=text("'active'")),
    Column("last_cursor", JSONB, nullable=True),

    Column("created_at", TIMESTAMP(timezone=True), server_default=func.now(), nullable=False),
    Column("updated_at", TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False),

    Index("ix_log_connectors_tenant", "tenant_id"),
    Index("ix_log_connectors_tenant_type", "tenant_id", "connector_type"),
)


log_field_mappings = Table(
    "log_field_mappings",
    metadata,

    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("connector_id", UUID(as_uuid=True), ForeignKey("log_connectors.id", ondelete="CASCADE"), nullable=False),
    Column("mapping_name", String(255), nullable=False),
    Column("field_mappings", JSONB, nullable=False),
    Column("is_default", Boolean, nullable=False, server_default=text("false")),

    Column("created_at", TIMESTAMP(timezone=True), server_default=func.now(), nullable=False),
    Column("updated_at", TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False),

    Index("ix_log_field_mappings_connector", "connector_id"),
    Index("ix_log_field_mappings_connector_default", "connector_id", "is_default"),
)


ingested_logs = Table(
    "ingested_logs",
    metadata,

    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("connector_id", UUID(as_uuid=True), ForeignKey("log_connectors.id", ondelete="CASCADE"), nullable=False),
    Column("raw_document", JSONB, nullable=False),
    Column("normalized_document", JSONB, nullable=False),
    Column("field_mapping_used", JSONB, nullable=False),
    Column("source_index", String(255), nullable=False),
    Column("source_doc_id", String(255), nullable=False),
    Column("log_timestamp", TIMESTAMP(timezone=True), nullable=False),
    Column("ingested_at", TIMESTAMP(timezone=True), server_default=func.now(), nullable=False),

    UniqueConstraint("connector_id", "source_doc_id", name="ux_ingested_logs_connector_doc"),
    Index("ix_ingested_logs_connector_ingested", "connector_id", "ingested_at"),
    Index("ix_ingested_logs_connector_timestamp", "connector_id", "log_timestamp"),
)


ai_ops_remedies = Table(
    "ai_ops_remedies",
    metadata,

    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("tenant_id", UUID(as_uuid=False), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
    Column("incident_id", String(255), nullable=True),
    Column("team", String(255), nullable=True),
    Column("priority", String(50), nullable=True),
    Column("incident_title", String(500), nullable=False),
    Column("summary", Text, nullable=True),
    Column("root_cause", Text, nullable=True),
    Column("email_subject", String(500), nullable=True),
    Column("status", String(50), nullable=False, server_default=text("'active'")),
    Column("incident_timestamp", TIMESTAMP(timezone=True), server_default=func.now(), nullable=False),
    Column("remedy", JSONB, nullable=True),
    Column("correlation_key", String(255), nullable=True),

    Column("created_at", TIMESTAMP(timezone=True), server_default=func.now(), nullable=False),
    Column("updated_at", TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False),

    Index("ix_ai_ops_remedies_tenant", "tenant_id"),
    Index("ix_ai_ops_remedies_tenant_status", "tenant_id", "status"),
    Index("ix_ai_ops_remedies_tenant_timestamp", "tenant_id", "incident_timestamp"),
    Index(
        "ux_ai_ops_remedies_tenant_corr_key",
        "tenant_id",
        "correlation_key",
        unique=True,
        postgresql_where=text("status = 'active' AND correlation_key IS NOT NULL"),
    ),
)


ai_ops_approvals = Table(
    "ai_ops_approvals",
    metadata,

    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("tenant_id", UUID(as_uuid=False), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
    Column("remedy_id", UUID(as_uuid=True), ForeignKey("ai_ops_remedies.id", ondelete="CASCADE"), nullable=False),
    Column("decision", String(50), nullable=False),  # overall: "pending" | "approved" | "declined"
    Column("decided_at", TIMESTAMP(timezone=True), nullable=True),  # set only when decision transitions to approved/declined
    Column("channel", String(50), nullable=True),  # last channel that acted (kept for compat)
    Column("approved_by", String(500), nullable=True),

    Column("app_decision", String(50), nullable=True),   # "approved" | "declined" | null
    Column("app_decided_at", TIMESTAMP(timezone=True), nullable=True),
    Column("email_decision", String(50), nullable=True),  # "approved" | "declined" | null
    Column("email_decided_at", TIMESTAMP(timezone=True), nullable=True),

    Column("created_at", TIMESTAMP(timezone=True), server_default=func.now(), nullable=False),
    Column("updated_at", TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False),

    UniqueConstraint("remedy_id", name="uq_ai_ops_approvals_remedy"),
    Index("ix_ai_ops_approvals_tenant", "tenant_id"),
    Index("ix_ai_ops_approvals_remedy", "remedy_id"),
)


ai_ops_sops = Table(
    "ai_ops_sops",
    metadata,

    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("tenant_id", UUID(as_uuid=False), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
    Column("name", String(500), nullable=False),
    Column("content", Text, nullable=True),
    Column("document_url", String(1000), nullable=True),

    Column("created_at", TIMESTAMP(timezone=True), server_default=func.now(), nullable=False),
    Column("updated_at", TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False),

    Index("ix_ai_ops_sops_tenant", "tenant_id"),
)


ai_ops_workflows = Table(
    "ai_ops_workflows",
    metadata,

    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("tenant_id", UUID(as_uuid=False), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
    Column("remedy_id", UUID(as_uuid=True), ForeignKey("ai_ops_remedies.id", ondelete="CASCADE"), nullable=False),
    Column("approval_id", UUID(as_uuid=True), ForeignKey("ai_ops_approvals.id", ondelete="CASCADE"), nullable=False),
    Column("status", String(50), nullable=False, server_default=text("'approved'")),
    Column("trigger_text", Text, nullable=True),
    Column("objective", Text, nullable=True),
    Column("steps", JSONB, nullable=True),

    Column("created_at", TIMESTAMP(timezone=True), server_default=func.now(), nullable=False),
    Column("updated_at", TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False),

    UniqueConstraint("remedy_id", name="uq_ai_ops_workflows_remedy"),
    Index("ix_ai_ops_workflows_tenant", "tenant_id"),
    Index("ix_ai_ops_workflows_remedy", "remedy_id"),
)


ai_ops_workflow_definitions = Table(
    "ai_ops_workflow_definitions",
    metadata,

    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("tenant_id", UUID(as_uuid=False), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
    Column("name", String(255), nullable=False),
    Column("sop_id", UUID(as_uuid=True), ForeignKey("ai_ops_sops.id", ondelete="SET NULL"), nullable=True),
    Column("trigger_condition", Text, nullable=True),
    Column("activepieces_flow_name", String(500), nullable=True),
    Column("status", String(50), nullable=False, server_default=text("'active'")),

    Column("created_at", TIMESTAMP(timezone=True), server_default=func.now(), nullable=False),
    Column("updated_at", TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False),

    UniqueConstraint("tenant_id", "name", name="uq_ai_ops_wf_defs_tenant_name"),
    Index("ix_ai_ops_wf_defs_tenant", "tenant_id"),
)


# ---------------------------------------------------------------------------
# Underwriting tables
# Managed by neutrino-database Alembic; used by connector-service AP flows.
# ---------------------------------------------------------------------------

underwriting_sessions = Table(
    "underwriting_sessions",
    metadata,

    Column("session_id", Text, primary_key=True),
    Column("application_id", Text, nullable=False),
    Column("applicant_name", Text, nullable=True),
    Column("email", Text, nullable=True),
    Column("address", Text, nullable=True),
    Column("loan_product", Text, nullable=True),
    Column("loan_amount", Numeric, nullable=True),
    Column("loan_tenure_months", Integer, nullable=True),
    Column("monthly_income", Numeric, nullable=True),
    Column("employer_name", Text, nullable=True),
    Column("loan_purpose", Text, nullable=True),
    Column("dti_threshold", Numeric, nullable=True, server_default=text("50")),
    Column("status", Text, nullable=True),
    Column("tenant_id", Text, nullable=True),
    Column("chat_started_at", TIMESTAMP(timezone=True), nullable=True),
    Column("created_at", TIMESTAMP(timezone=True), server_default=func.now(), nullable=True),
    Column("updated_at", TIMESTAMP(timezone=True), server_default=func.now(), nullable=True),
)


underwriting_conversation_history = Table(
    "underwriting_conversation_history",
    metadata,

    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("session_id", Text, ForeignKey("underwriting_sessions.session_id", ondelete="CASCADE"), nullable=False),
    Column("turn_index", Integer, nullable=False),
    Column("role", Text, nullable=False),
    Column("message", Text, nullable=True),
    Column("message_type", Text, nullable=True),
    Column("conversation_state", Text, nullable=True),
    Column("metadata", JSONB, nullable=True),

    UniqueConstraint("session_id", "turn_index", name="uq_conversation_history_session_turn"),
    Index("ix_conversation_history_session", "session_id"),
)


underwriting_session_documents = Table(
    "underwriting_session_documents",
    metadata,

    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("session_id", Text, ForeignKey("underwriting_sessions.session_id", ondelete="CASCADE"), nullable=False),
    Column("doc_type", Text, nullable=False),
    Column("minio_key", Text, nullable=True),
    Column("minio_url", Text, nullable=True),
    Column("extracted_text", Text, nullable=True),
    Column("validation_status", Text, nullable=True),
    Column("uploaded_at", TIMESTAMP(timezone=True), server_default=func.now(), nullable=True),
    Column("validated_at", TIMESTAMP(timezone=True), nullable=True),

    UniqueConstraint("session_id", "doc_type", name="uq_session_documents_session_doctype"),
    Index("ix_session_documents_session", "session_id"),
)


underwriting_pipeline_results = Table(
    "underwriting_pipeline_results",
    metadata,

    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("session_id", Text, ForeignKey("underwriting_sessions.session_id", ondelete="CASCADE"), nullable=False),
    Column("flow_name", Text, nullable=False),
    Column("status", Text, nullable=True),
    Column("result_json", JSONB, nullable=True),
    Column("error_message", Text, nullable=True),
    Column("started_at", TIMESTAMP(timezone=True), server_default=func.now(), nullable=True),
    Column("completed_at", TIMESTAMP(timezone=True), nullable=True),

    UniqueConstraint("session_id", "flow_name", name="uq_pipeline_results_session_flow"),
    Index("ix_pipeline_results_session", "session_id"),
)


underwriting_rules = Table(
    "underwriting_rules",
    metadata,

    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", Text, nullable=False),
    Column("description", Text, nullable=True),
    Column("category", Text, nullable=True),
    Column("severity", Text, nullable=True, server_default=text("'medium'")),
    Column("condition", Text, nullable=True),
    Column("threshold", Text, nullable=True),
    Column("enabled", Boolean, nullable=True, server_default=text("true")),
    Column("created_at", TIMESTAMP(timezone=True), server_default=func.now(), nullable=True),
    Column("updated_at", TIMESTAMP(timezone=True), server_default=func.now(), nullable=True),
)


# ---------------------------------------------------------------------------
# audit_log — append-only compliance event store (NEU-1804, slice C3a).
#
# Every meaningful mutation in the gateway writes a row here. Required by
# SOC 2 (CC6.6), HIPAA (§ 164.312(b)), and GDPR (Art 30, 32). The
# emitter helper lives in the gateway; this is just the storage.
#
# Hard rule: append-only. The BEFORE UPDATE/DELETE trigger below raises
# SQLSTATE 'AU001' so the immutability invariant holds at the database
# level — auditors won't accept "we promise we don't update it."
#
# See user-stories/user-lifecycle.md § "Audit log requirements" for the
# product-level specification and event-type catalog.
# ---------------------------------------------------------------------------

audit_log = Table(
    "audit_log",
    metadata,

    Column("id", UUID(as_uuid=False), primary_key=True, default=uuid.uuid4),
    # FK is NO ACTION (default), not CASCADE: a tenant cannot be hard-deleted
    # while audit history references it. The retention runner clears audit_log
    # rows past their window first; tenant teardown happens after.
    Column("tenant_id", UUID(as_uuid=False), ForeignKey("tenant.id"), nullable=False),
    # Nullable so system-initiated events (cron jobs, runners) can record without an actor.
    # SET NULL: when a user is eventually hard-deleted (post-retention), preserve the
    # audit entry but null out the actor reference.
    Column("actor_user_id", UUID(as_uuid=False), ForeignKey("user.id", ondelete="SET NULL"), nullable=True),

    # Closed catalog — see gateway emitter. Stored as TEXT so the catalog can
    # evolve without alembic churn; PR review enforces additions to the catalog.
    Column("event_type", Text, nullable=False),
    Column("resource_type", Text, nullable=False),
    Column("resource_id", Text, nullable=False),

    # Event-specific structured payload. The emitter is responsible for
    # never putting raw PII into this column — references IDs only.
    # Renamed from `metadata` to avoid clashing with SA DeclarativeBase.metadata.
    Column("event_metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")),

    # Optional client-side context. PII-tagged so the C6 anonymization runner
    # can wipe these when the actor is erased.
    Column("ip_address", INET, nullable=True, comment="pii:ipaddress"),
    Column("user_agent", Text, nullable=True, comment="pii:freetext"),

    Column("occurred_at", TIMESTAMP(timezone=True), server_default=func.now(), nullable=False),

    # Tenant-scoped read path: latest events first.
    Index("ix_audit_log_tenant_occurred_at", "tenant_id", text("occurred_at DESC")),
    # Filter by event_type (e.g. show me all workspace.deleted in this tenant).
    Index("ix_audit_log_event_type", "event_type"),
    # "What did user X do" — partial index keeps it small (skips system events).
    Index(
        "ix_audit_log_actor_occurred_at",
        "actor_user_id",
        text("occurred_at DESC"),
        postgresql_where=text("actor_user_id IS NOT NULL"),
    ),
)


# Immutability trigger. Installed via SQLAlchemy event hooks so that
# both Base.metadata.create_all (used by tests) and the alembic
# migration (used in real DBs) end up with the same DDL on the table.
#
# Split into individual statements because asyncpg doesn't support
# multi-statement prepared statements.
_AUDIT_LOG_CREATE_FUNCTION = DDL(
    """
    CREATE OR REPLACE FUNCTION audit_log_block_mutation() RETURNS trigger AS $func$
    BEGIN
        RAISE EXCEPTION 'audit_log is append-only; UPDATE/DELETE blocked'
            USING ERRCODE = 'AU001';
    END;
    $func$ LANGUAGE plpgsql
    """
)
_AUDIT_LOG_DROP_TRIGGER = DDL(
    "DROP TRIGGER IF EXISTS audit_log_immutability ON audit_log"
)
_AUDIT_LOG_CREATE_TRIGGER = DDL(
    """
    CREATE TRIGGER audit_log_immutability
        BEFORE UPDATE OR DELETE ON audit_log
        FOR EACH ROW EXECUTE FUNCTION audit_log_block_mutation()
    """
)
_AUDIT_LOG_DROP_FUNCTION = DDL(
    "DROP FUNCTION IF EXISTS audit_log_block_mutation()"
)

# After-create: function first, then trigger (idempotent — drop-if-exists first).
event.listen(audit_log, "after_create", _AUDIT_LOG_CREATE_FUNCTION.execute_if(dialect="postgresql"))
event.listen(audit_log, "after_create", _AUDIT_LOG_DROP_TRIGGER.execute_if(dialect="postgresql"))
event.listen(audit_log, "after_create", _AUDIT_LOG_CREATE_TRIGGER.execute_if(dialect="postgresql"))

# Before-drop: trigger first, then function.
event.listen(audit_log, "before_drop", _AUDIT_LOG_DROP_TRIGGER.execute_if(dialect="postgresql"))
event.listen(audit_log, "before_drop", _AUDIT_LOG_DROP_FUNCTION.execute_if(dialect="postgresql"))


# ─────────────────────────────────────────────────────────────────
# tenancy_ownership_transfer (NEU-X3)
# ─────────────────────────────────────────────────────────────────
#
# Two-step ownership transfer per user-stories/tenant-admin-actions.md
# § 4. Primary Owner initiates a transfer to a target Tenant Admin;
# the target accepts via an email link within 7 days; the atomic
# UPDATE swaps tenant.tenant_owner. The retention runner cancels
# expired pending transfers nightly.
tenancy_ownership_transfer = Table(
    "tenancy_ownership_transfer",
    metadata,
    Column("id", UUID(as_uuid=False), primary_key=True, default=uuid.uuid4),
    Column(
        "tenant_id",
        UUID(as_uuid=False),
        ForeignKey("tenant.id", ondelete="CASCADE"),
        nullable=False,
    ),
    # SET NULL on user delete: the transfer record survives a GDPR
    # erasure of the actor; audit_log.actor_user_id captures the
    # identity at time-of-action, which is what auditors care about.
    Column(
        "from_user_id",
        UUID(as_uuid=False),
        ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
    ),
    Column(
        "to_user_id",
        UUID(as_uuid=False),
        ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
    ),
    # Random hex string used in the FE accept URL. Globally unique
    # so the URL alone identifies the transfer; eliminates the need
    # for the FE to know the tenant_id when handling /tenants/transfer/{token}.
    Column("token", Text, nullable=False, unique=True),
    Column("expires_at", TIMESTAMP(timezone=True), nullable=False),
    Column("accepted_at", TIMESTAMP(timezone=True), nullable=True),
    Column("cancelled_at", TIMESTAMP(timezone=True), nullable=True),
    Column(
        "created_at",
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    ),
    # Only ONE pending transfer per tenant at a time. Without this
    # an Owner could fire off competing transfers and we'd race over
    # which token wins. accepted_at IS NULL AND cancelled_at IS NULL
    # captures "still pending" — the runner cancels expired ones.
    Index(
        "ux_ownership_transfer_pending_per_tenant",
        "tenant_id",
        unique=True,
        postgresql_where=text(
            "accepted_at IS NULL AND cancelled_at IS NULL"
        ),
    ),
    Index("ix_ownership_transfer_token", "token"),
    # Partial read index for the retention runner's expiry sweep.
    Index(
        "ix_ownership_transfer_pending_expires",
        "expires_at",
        postgresql_where=text(
            "accepted_at IS NULL AND cancelled_at IS NULL"
        ),
    ),
)


# ============================================================================
# Data Analytics — canonical metadata schema (NEU-1811 DA-P0).
#
# Seven tables encode the DA pillar's per-warehouse curated state. Spec:
# ``product-feature-roadmap/data-analytics/data-flow.md`` §4.8.
#
# Service ownership (feature.md F4):
#   * ``da_connection`` — connector-service owns lifecycle CRUD
#   * the six workspace_metadata_* / metric / join_hint / description_version
#     tables — agent-platform owns every write (metadata sync, LLM calls,
#     curation acceptance, etc.)
# ============================================================================


# ---------------------------------------------------------------------------
# da_connection — tenant-level Connection (Step 1 in data-flow.md).
#
# One row per tenant warehouse credential. Same physical warehouse can be
# represented by two rows (e.g. two Snowflake accounts on one tenant) — the
# unique key is (tenant_id, source_type, connection_name).
#
# Distinct from the legacy ``connections`` table above (which is the ES
# connector table — SharePoint / Drive workspace-scoped OAuth). The two
# entities have different semantics; co-locating them would be the kind
# of conflation called out in feature.md F4.
# ---------------------------------------------------------------------------

da_connection = Table(
    "da_connection",
    metadata,

    Column("id", UUID(as_uuid=False), primary_key=True, default=uuid.uuid4),
    Column(
        "tenant_id",
        UUID(as_uuid=False),
        ForeignKey("tenant.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "source_type",
        PgEnum(
            DASourceTypeEnum,
            name="da_source_type",
            values_callable=lambda enum: [e.value for e in enum],
        ),
        nullable=False,
    ),
    Column("connection_name", String(255), nullable=False),
    # KMS-wrapped credentials blob. JSONB so the adapter can pack arbitrary
    # shape (password vs key-pair vs service-account JSON). PII-tagged so
    # the C6 anonymization runner finds it.
    Column(
        "credentials",
        JSONB,
        nullable=False,
        comment="pii:credentials",
    ),
    Column(
        "status",
        PgEnum(
            DAConnectionStatusEnum,
            name="da_connection_status",
            values_callable=lambda enum: [e.value for e in enum],
        ),
        nullable=False,
        server_default=text("'pending_auth'"),
    ),
    # Tenant-level schema allowlist (NEU-1811 DA-P1f).
    #   NULL          → unrestricted; workspace admins see every schema
    #                   the warehouse exposes.
    #   list[str]     → whitelist; only these schemas are visible to
    #                   workspace admins and queryable via execute_query.
    # Enforced at the connector-service adapter / endpoint layer; this
    # column is the source-of-truth.
    Column("allowed_schemas", JSONB, nullable=True),
    # SET NULL so a user erasure (GDPR Art 17) doesn't take the connection
    # down with the actor row.
    Column(
        "created_by",
        UUID(as_uuid=False),
        ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
    ),
    Column(
        "created_at",
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    ),
    Column(
        "updated_at",
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    ),

    # Uniqueness scope per data-flow.md §1: "unique among that tenant's
    # <source> connections". Cross-source name collisions are fine.
    Index(
        "ux_da_connection_tenant_source_name",
        "tenant_id",
        "source_type",
        "connection_name",
        unique=True,
    ),
    Index("ix_da_connection_tenant", "tenant_id"),
)


# ---------------------------------------------------------------------------
# da_catalog_schema / da_catalog_table / da_catalog_column — tenant-level
# facts about what's in the warehouse (DA-P1g refactor).
#
# Why these are tenant-scoped, not workspace-scoped: a column either IS
# or ISN'T PII; "users.email" has one true type regardless of which
# workspace is looking at it. Production catalog systems (Looker, dbt,
# Hex, Metabase) all separate the catalog (facts) from per-team curation
# (opinions). Workspace-level enrichment lives on the
# workspace_curation_da_* overlays below.
# ---------------------------------------------------------------------------

da_catalog_schema = Table(
    "da_catalog_schema",
    metadata,

    Column("id", UUID(as_uuid=False), primary_key=True, default=uuid.uuid4),
    Column(
        "da_connection_id",
        UUID(as_uuid=False),
        ForeignKey("da_connection.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("schema_name", String(255), nullable=False),
    Column("schema_description", Text, nullable=True),
    # Compliance classification — see DA-P1i.3. Schema-level tags
    # propagate to every table + column inside (effective-at-read).
    Column(
        "is_pii",
        Boolean,
        nullable=False,
        server_default=text("false"),
    ),
    Column(
        "is_restricted",
        Boolean,
        nullable=False,
        server_default=text("false"),
    ),
    Column("last_synced_at", TIMESTAMP(timezone=True), nullable=True),
    Column(
        "created_at",
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    ),
    Column(
        "updated_at",
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    ),

    Index(
        "ux_da_catalog_schema_conn_name",
        "da_connection_id",
        "schema_name",
        unique=True,
    ),
    Index("ix_da_catalog_schema_conn", "da_connection_id"),
)


da_catalog_table = Table(
    "da_catalog_table",
    metadata,

    Column("id", UUID(as_uuid=False), primary_key=True, default=uuid.uuid4),
    Column(
        "da_catalog_schema_id",
        UUID(as_uuid=False),
        ForeignKey("da_catalog_schema.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("table_name", String(255), nullable=False),
    Column(
        "table_type",
        PgEnum(
            DATableTypeEnum,
            name="da_table_type",
            values_callable=lambda enum: [e.value for e in enum],
            create_type=False,
        ),
        nullable=False,
        server_default=text("'table'"),
    ),
    Column("native_comment", Text, nullable=True),
    Column("row_count", BigInteger, nullable=True),
    # Table-level compliance classification — see DA-P1i.3. Propagates
    # to every column in this table (effective-at-read).
    Column(
        "is_pii",
        Boolean,
        nullable=False,
        server_default=text("false"),
    ),
    Column(
        "is_restricted",
        Boolean,
        nullable=False,
        server_default=text("false"),
    ),
    Column("last_synced_at", TIMESTAMP(timezone=True), nullable=True),
    Column(
        "created_at",
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    ),
    Column(
        "updated_at",
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    ),

    Index(
        "ux_da_catalog_table_schema_name",
        "da_catalog_schema_id",
        "table_name",
        unique=True,
    ),
    Index("ix_da_catalog_table_schema", "da_catalog_schema_id"),
)


# ---------------------------------------------------------------------------
# da_catalog_column — TWO-WRITER row with documented column ownership.
#
# Multiple services write to this row on different columns; this is the
# fine pattern (each column has a single owner). See
# `product-feature-roadmap/data-analytics/description-generation.md`
# discussion log 2026-05-12 — "Classification stays in connector-service".
#
# Column ownership:
#
#   * Sync (connector-service.ConnectionService.sync_catalog):
#       column_name, data_type, nullable, is_primary_key, is_foreign_key,
#       foreign_key_to, native_comment, ordinal_position, last_synced_at,
#       created_at, updated_at
#
#   * Classification (connector-service.ConnectionService
#     .patch_catalog_column_classification):
#       is_pii, is_restricted
#
# Hard invariant: sync's UPDATE branch MUST NOT touch is_pii / is_restricted
# (would race against classification). Sync writes are upserts that
# preserve classification state on existing rows.
# ---------------------------------------------------------------------------

da_catalog_column = Table(
    "da_catalog_column",
    metadata,

    Column("id", UUID(as_uuid=False), primary_key=True, default=uuid.uuid4),
    Column(
        "da_catalog_table_id",
        UUID(as_uuid=False),
        ForeignKey("da_catalog_table.id", ondelete="CASCADE"),
        nullable=False,
    ),

    # DDL-derived facts
    Column("column_name", String(255), nullable=False),
    Column("data_type", String(255), nullable=False),
    Column("nullable", Boolean, nullable=False),
    Column(
        "is_primary_key",
        Boolean,
        nullable=False,
        server_default=text("false"),
    ),
    Column(
        "is_foreign_key",
        Boolean,
        nullable=False,
        server_default=text("false"),
    ),
    # List of {target_schema, target_table, target_column}.
    Column("foreign_key_to", JSONB, nullable=True),
    Column("native_comment", Text, nullable=True),
    Column("ordinal_position", Integer, nullable=False),

    # Compliance classification — tenant-owned, no workspace override
    # for is_pii at all; is_restricted can only be upgraded by workspace
    # via workspace_curation_da_column.is_restricted_override.
    Column(
        "is_pii",
        Boolean,
        nullable=False,
        server_default=text("false"),
    ),
    Column(
        "is_restricted",
        Boolean,
        nullable=False,
        server_default=text("false"),
    ),

    Column("last_synced_at", TIMESTAMP(timezone=True), nullable=True),
    Column(
        "created_at",
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    ),
    Column(
        "updated_at",
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    ),

    Index(
        "ux_da_catalog_column_table_name",
        "da_catalog_table_id",
        "column_name",
        unique=True,
    ),
    Index("ix_da_catalog_column_table", "da_catalog_table_id"),
)


# ---------------------------------------------------------------------------
# workspace_curation_da_table / workspace_curation_da_column — workspace
# opinion overlays on top of the tenant catalog (DA-P1g refactor).
#
# Thin rows: "this workspace exposes this catalog row to its users",
# plus per-workspace AI / admin descriptions, synonyms, sample values,
# etc. The same column can be described differently for different teams
# (sales workspace ≠ finance workspace), so enrichment lives here.
# Compliance classification (is_pii / is_restricted) lives on the
# catalog — a workspace cannot disagree about PII status.
# ---------------------------------------------------------------------------

workspace_curation_da_table = Table(
    "workspace_curation_da_table",
    metadata,

    Column("id", UUID(as_uuid=False), primary_key=True, default=uuid.uuid4),
    Column(
        "workspace_id",
        UUID(as_uuid=False),
        ForeignKey("workspace.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "da_catalog_table_id",
        UUID(as_uuid=False),
        ForeignKey("da_catalog_table.id", ondelete="CASCADE"),
        nullable=False,
    ),

    # Per-workspace opinion / context.
    #
    # DA-P1l.1.0 collapsed the two-field model (admin_seed_description +
    # ai_generated_description) into a single ``description`` field with
    # trust metadata below. See description-generation.md §M1, M2.
    Column("table_logical_name", String(255), nullable=True),
    Column("description", Text, nullable=True),
    # DA-P1k.1 — workspace-scoped alt names; same shape as the
    # equivalent ``workspace_curation_da_column.synonyms``. NULL =
    # not set; empty list semantically equivalent.
    Column("synonyms", JSONB, nullable=True),

    # Trust metadata (M2). origin records who wrote the current
    # description text — 'human' or 'ai'. Admin edits flip it to 'human'
    # and clear ai_accepted_at; Generate / Regenerate flip it to 'ai'
    # and stamp ai_last_generated_at. ai_accepted_at is the HITL gate:
    # chat (T2S) trusts an ai-origin description only when this is set.
    Column(
        "description_origin",
        String(8),
        nullable=False,
        server_default=text("'human'"),
    ),
    Column("ai_accepted_at", TIMESTAMP(timezone=True), nullable=True),
    Column("ai_last_generated_at", TIMESTAMP(timezone=True), nullable=True),

    # Curation
    Column(
        "is_included",
        Boolean,
        nullable=False,
        server_default=text("false"),
    ),
    Column(
        "is_archived",
        Boolean,
        nullable=False,
        server_default=text("false"),
    ),
    Column("last_enriched_at", TIMESTAMP(timezone=True), nullable=True),
    Column(
        "created_at",
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    ),
    Column(
        "updated_at",
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    ),

    CheckConstraint(
        "description_origin IN ('human', 'ai')",
        name="ck_wcdt_description_origin",
    ),
    Index(
        "ux_wcdt_workspace_catalog",
        "workspace_id",
        "da_catalog_table_id",
        unique=True,
    ),
    Index("ix_wcdt_workspace", "workspace_id"),
    Index("ix_wcdt_catalog", "da_catalog_table_id"),
)


workspace_curation_da_column = Table(
    "workspace_curation_da_column",
    metadata,

    Column("id", UUID(as_uuid=False), primary_key=True, default=uuid.uuid4),
    Column(
        "workspace_id",
        UUID(as_uuid=False),
        ForeignKey("workspace.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "da_catalog_column_id",
        UUID(as_uuid=False),
        ForeignKey("da_catalog_column.id", ondelete="CASCADE"),
        nullable=False,
    ),

    # Per-workspace LLM context.
    #
    # DA-P1l.1.0 collapsed the two-field model into a single ``description``
    # field with trust metadata below. See description-generation.md §M1, M2.
    Column("column_logical_name", String(255), nullable=True),
    Column("description", Text, nullable=True),
    Column("synonyms", JSONB, nullable=True),
    Column("unit", String(64), nullable=True),
    Column("format_hint", String(64), nullable=True),
    Column("valid_aggregations", JSONB, nullable=True),

    # Trust metadata (M2). Same semantics as workspace_curation_da_table.
    Column(
        "description_origin",
        String(8),
        nullable=False,
        server_default=text("'human'"),
    ),
    Column("ai_accepted_at", TIMESTAMP(timezone=True), nullable=True),
    Column("ai_last_generated_at", TIMESTAMP(timezone=True), nullable=True),

    # Phase-2 enrichment. DA-P1l.1.0 lifted the sampling toggle to the
    # workspace level (workspace_da_settings.da_include_sample_values)
    # per M11 — per-column was redundant because catalog flags
    # (PII / Restricted) already hard-block sampling and is_included
    # already controls whether the column is curated at all.
    # sample_values can hold real PII from the warehouse — tagged so the
    # C6 anonymization runner can null these on user erasure.
    Column(
        "sample_values",
        JSONB,
        nullable=True,
        comment="pii:freetext",
    ),
    Column("cardinality_score", Float, nullable=True),
    Column("statistical_profile", JSONB, nullable=True),

    # Upgrade-only restricted override (compliance posture).
    Column(
        "is_restricted_override",
        Boolean,
        nullable=False,
        server_default=text("false"),
    ),

    # Curation
    Column(
        "is_included",
        Boolean,
        nullable=False,
        server_default=text("false"),
    ),
    Column(
        "is_archived",
        Boolean,
        nullable=False,
        server_default=text("false"),
    ),
    Column("last_enriched_at", TIMESTAMP(timezone=True), nullable=True),
    Column(
        "created_at",
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    ),
    Column(
        "updated_at",
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    ),

    CheckConstraint(
        "description_origin IN ('human', 'ai')",
        name="ck_wcdc_description_origin",
    ),
    Index(
        "ux_wcdc_workspace_catalog",
        "workspace_id",
        "da_catalog_column_id",
        unique=True,
    ),
    Index("ix_wcdc_workspace", "workspace_id"),
    Index("ix_wcdc_catalog", "da_catalog_column_id"),
)


# ---------------------------------------------------------------------------
# workspace_da_settings — workspace-level DA settings (DA-P1l.1.0).
#
# Holds workspace-level toggles that govern AI description generation
# behaviour. See M11 in product-feature-roadmap/data-analytics/
# description-generation.md. One row per workspace, PK == FK to
# workspace(id). Row is lazy-created on first PATCH; absence means
# defaults apply.
#
# Future DA workspace settings (default model preference, cost cap,
# etc.) land here rather than as JSONB sprawl on the workspace row.
# ---------------------------------------------------------------------------

workspace_da_settings = Table(
    "workspace_da_settings",
    metadata,

    Column(
        "workspace_id",
        UUID(as_uuid=False),
        ForeignKey("workspace.id", ondelete="CASCADE"),
        primary_key=True,
    ),

    # M11 toggles. Both default TRUE (fail-safe).
    #
    # da_include_sample_values: whether the TOP VALUES block appears in
    # column prompts. PII/Restricted columns are skipped regardless
    # (catalog hard-gate, M10).
    #
    # da_pii_redaction_enabled: whether to wrap LLM calls in GovernedLLM
    # (PII pattern redaction in-flight). Reduces description quality
    # when on — recommended only if workspace's LLM provider isn't a
    # trusted private tenant.
    Column(
        "da_include_sample_values",
        Boolean,
        nullable=False,
        server_default=text("true"),
    ),
    Column(
        "da_pii_redaction_enabled",
        Boolean,
        nullable=False,
        server_default=text("true"),
    ),

    Column(
        "created_at",
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    ),
    Column(
        "updated_at",
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    ),
)


# ---------------------------------------------------------------------------
# workspace_integration_settings — per-workspace connector governance policy
# (WF-CF-1b). Cross-pillar (NOT DA-specific): the workspace-admin switches
# that gate how members may use connectors here. One row per workspace,
# lazy-created on first write; NO ROW = defaults (fail-safe = permissive,
# matching workspace_da_settings).
# ---------------------------------------------------------------------------
workspace_integration_settings = Table(
    "workspace_integration_settings",
    metadata,
    Column(
        "workspace_id",
        UUID(as_uuid=False),
        ForeignKey("workspace.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    # Whether members may connect their own (personal) integrations here.
    # Even when ON, a provider must also declare personal support in its
    # catalog (owner_support) for a personal connect to be offered.
    Column(
        "allow_personal_integrations",
        Boolean,
        nullable=False,
        server_default=text("true"),
    ),
    # Whether a workflow whose derived scope is personal / per-member may run
    # in this workspace (PRD §13). Declared now to avoid a re-migration.
    Column(
        "allow_personal_scoped_workflows",
        Boolean,
        nullable=False,
        server_default=text("true"),
    ),
    Column(
        "created_at",
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    ),
    Column(
        "updated_at",
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    ),
)


# ---------------------------------------------------------------------------
# workspace_da_access_grant — per-member ACL projection (X-DA-ACL-1).
#
# One row per (workspace_id, user_id, resource_type, resource_id)
# tuple. Stores explicit grants and denies on DA catalog resources
# at any depth (schema / table / column). The absence of a row at a
# given level means "inherit from parent" — resolution walks the
# resource tree from leaf upward, applying the closest explicit
# row. Resolution rule lives in the service (not the schema)
# because it needs the catalog tree, but the storage shape is
# minimal and indexed for the two UI read paths:
#
#   1. "All grants for member B in workspace W" → drives the
#      member-summary view in workspace-settings/members.
#   2. "All grants on resource R in workspace W" → drives the
#      Access drawer when an admin clicks the chip on a catalog row.
#
# Tenant Owner / Tenant Admin / Workspace Admin bypass entirely via
# the JWT projection — they never write grant rows against
# themselves. M10 PII / Restricted hard-blocks layer above this
# unconditionally.
# ---------------------------------------------------------------------------

workspace_da_access_grant = Table(
    "workspace_da_access_grant",
    metadata,

    Column("id", UUID(as_uuid=False), primary_key=True, default=uuid.uuid4),
    Column(
        "workspace_id",
        UUID(as_uuid=False),
        ForeignKey("workspace.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "user_id",
        UUID(as_uuid=False),
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
    ),

    # Which level of the catalog tree this grant targets. The
    # ``resource_id`` column carries the catalog row's UUID matching
    # the level (da_catalog_schema.id / da_catalog_table.id /
    # da_catalog_column.id). We deliberately don't FK ``resource_id``
    # to the three catalog tables — that would require a polymorphic
    # FK shape (one column, three possible targets) which Postgres
    # can't express natively. The service is responsible for
    # validating resource_id belongs to a row of the matching type
    # in the caller's workspace before insert.
    Column(
        "resource_type",
        PgEnum(
            DAAccessResourceTypeEnum,
            name="da_access_resource_type",
            values_callable=lambda enum: [e.value for e in enum],
        ),
        nullable=False,
    ),
    Column("resource_id", UUID(as_uuid=False), nullable=False),

    # Explicit allow or deny. Inherit-from-parent is the *absence* of
    # a row at this level — never stored.
    Column(
        "effect",
        PgEnum(
            DAAccessEffectEnum,
            name="da_access_effect",
            values_callable=lambda enum: [e.value for e in enum],
        ),
        nullable=False,
    ),

    Column("created_by", UUID(as_uuid=False), ForeignKey("user.id", ondelete="SET NULL"), nullable=False),
    Column("created_at", TIMESTAMP(timezone=True), server_default=func.now(), nullable=False),
    Column("updated_at", TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False),

    # One effect per member per resource. Without this the UI couldn't
    # decide what 'current state' means for a cell in the matrix.
    UniqueConstraint(
        "workspace_id",
        "user_id",
        "resource_type",
        "resource_id",
        name="ux_workspace_da_access_grant_member_resource",
    ),
    # Member-summary lookup ("what does Bob have access to?").
    Index(
        "ix_workspace_da_access_grant_workspace_user",
        "workspace_id",
        "user_id",
    ),
    # Resource-drawer lookup ("who has access to this column?").
    Index(
        "ix_workspace_da_access_grant_workspace_resource",
        "workspace_id",
        "resource_type",
        "resource_id",
    ),
)


# ---------------------------------------------------------------------------
# metric — Entity 5 (§4.8).
#
# Workspace-scoped business metric. Independent HITL lifecycle (admin
# accepts/rejects AI suggestions). Partial unique on (workspace_id, name)
# WHERE is_archived = false — archiving a metric frees its name for reuse.
# ---------------------------------------------------------------------------

metric = Table(
    "metric",
    metadata,

    Column("id", UUID(as_uuid=False), primary_key=True, default=uuid.uuid4),
    Column(
        "workspace_id",
        UUID(as_uuid=False),
        ForeignKey("workspace.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("name", String(255), nullable=False),
    Column("description", Text, nullable=True),
    Column("sql_expression", Text, nullable=False),
    Column("filters", Text, nullable=True),
    # List of table_name strings the metric applies to.
    Column("applicable_tables", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    # List of column_name strings — dimensions the metric can be grouped by.
    Column("valid_dimensions", JSONB, nullable=True),
    Column(
        "source",
        PgEnum(
            DAMetricSourceEnum,
            name="da_metric_source",
            values_callable=lambda enum: [e.value for e in enum],
        ),
        nullable=False,
        server_default=text("'admin_authored'"),
    ),
    Column(
        "accepted",
        Boolean,
        nullable=False,
        server_default=text("false"),
    ),
    Column(
        "created_by",
        UUID(as_uuid=False),
        ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
    ),
    Column(
        "updated_by",
        UUID(as_uuid=False),
        ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
    ),
    Column("last_used_at", TIMESTAMP(timezone=True), nullable=True),
    Column(
        "is_archived",
        Boolean,
        nullable=False,
        server_default=text("false"),
    ),
    Column(
        "created_at",
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    ),
    Column(
        "updated_at",
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    ),

    # Partial unique — archived rows don't block reusing the name.
    Index(
        "ux_metric_workspace_name_active",
        "workspace_id",
        "name",
        unique=True,
        postgresql_where=text("is_archived = false"),
    ),
    Index("ix_metric_workspace", "workspace_id"),
)


# ---------------------------------------------------------------------------
# join_hint — Entity 6 (§4.8).
#
# Workspace-scoped join hint. Cascades when either side table is removed
# (the hint becomes meaningless).
# ---------------------------------------------------------------------------

join_hint = Table(
    "join_hint",
    metadata,

    Column("id", UUID(as_uuid=False), primary_key=True, default=uuid.uuid4),
    Column(
        "workspace_id",
        UUID(as_uuid=False),
        ForeignKey("workspace.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "left_table_id",
        UUID(as_uuid=False),
        ForeignKey("workspace_curation_da_table.id", ondelete="CASCADE"),
        nullable=False,
    ),
    # JSONB list[str] — composite join keys supported (e.g. ["tenant_id", "user_id"]).
    Column("left_columns", JSONB, nullable=False),
    Column(
        "right_table_id",
        UUID(as_uuid=False),
        ForeignKey("workspace_curation_da_table.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("right_columns", JSONB, nullable=False),
    Column(
        "join_type",
        PgEnum(
            DAJoinTypeEnum,
            name="da_join_type",
            values_callable=lambda enum: [e.value for e in enum],
        ),
        nullable=False,
        server_default=text("'inner'"),
    ),
    Column("semantic_description", Text, nullable=True),
    Column(
        "source",
        PgEnum(
            DAJoinHintSourceEnum,
            name="da_join_hint_source",
            values_callable=lambda enum: [e.value for e in enum],
        ),
        nullable=False,
        server_default=text("'admin_authored'"),
    ),
    Column(
        "accepted",
        Boolean,
        nullable=False,
        server_default=text("false"),
    ),
    Column(
        "created_by",
        UUID(as_uuid=False),
        ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
    ),
    Column(
        "is_archived",
        Boolean,
        nullable=False,
        server_default=text("false"),
    ),
    Column(
        "created_at",
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    ),

    Index("ix_join_hint_workspace", "workspace_id"),
    Index("ix_join_hint_left_table", "left_table_id"),
    Index("ix_join_hint_right_table", "right_table_id"),
)


# ---------------------------------------------------------------------------
# description_version — Entity 8 (§4.8). Append-only history.
#
# Soft-FK pattern: ``parent_id`` references one of four parent tables; the
# ``scope`` column discriminates. Postgres doesn't natively support
# discriminated FKs, so the parent FK is service-enforced (agent-platform
# writes never insert mismatched (scope, parent_id) pairs).
#
# No ``updated_at`` — a correction is a new version, not an in-place edit.
# Service-layer enforcement; DB-level immutability trigger deferred unless
# audit pressure later demands it (see AUDIT.md for the call).
# ---------------------------------------------------------------------------

description_version = Table(
    "description_version",
    metadata,

    Column("id", UUID(as_uuid=False), primary_key=True, default=uuid.uuid4),
    Column(
        "scope",
        PgEnum(
            DADescriptionScopeEnum,
            name="da_description_scope",
            values_callable=lambda enum: [e.value for e in enum],
        ),
        nullable=False,
    ),
    # Soft FK — see note above. parent_id references whichever table the
    # `scope` value points at: workspace_metadata_table /
    # workspace_metadata_column / metric / join_hint.
    Column("parent_id", UUID(as_uuid=False), nullable=False),
    Column("version_number", Integer, nullable=False),
    Column(
        "source",
        PgEnum(
            DADescriptionSourceEnum,
            name="da_description_source",
            values_callable=lambda enum: [e.value for e in enum],
        ),
        nullable=False,
    ),
    Column("content", Text, nullable=False),
    Column(
        "generated_at",
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    ),
    # SET NULL so a user erasure doesn't destroy the version row itself.
    Column(
        "generated_by",
        UUID(as_uuid=False),
        ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
    ),
    # For ai_generated / ai_suggested versions: DDL + comments + seed +
    # samples + stats used at generation time. Reproducible + eval-replayable.
    # May contain sample_values → PII-tagged.
    Column(
        "inputs_snapshot",
        JSONB,
        nullable=True,
        comment="pii:freetext",
    ),

    # version_number is auto-incremented per (scope, parent_id) — only one
    # row at each version. Service layer computes the next number on insert.
    Index(
        "ux_description_version_parent_version",
        "scope",
        "parent_id",
        "version_number",
        unique=True,
    ),
    # Latest-first read path: "give me the current description for this column".
    Index(
        "ix_description_version_parent_latest",
        "scope",
        "parent_id",
        text("version_number DESC"),
    ),
)


# ---------------------------------------------------------------------------
# Dashboards (NEU-1811 DA-P3.1). Workspace-scoped authored surfaces
# composed of widgets that pull from the curated DA catalog. Draft +
# Publish lifecycle. Each dashboard has a 1:1 build chat (kind=
# 'dashboard_build') and an optional set of link-tokens for external
# share. Multi-schema by design — a single dashboard can compose
# widgets across every schema the workspace has enabled.
#
# Design source: this session's DA-P3 lock + data-analytics.md
# D3 / D5 / D6 / D7 / D11 / D12.
# ---------------------------------------------------------------------------

dashboard = Table(
    "dashboard",
    metadata,

    Column("id", UUID(as_uuid=False), primary_key=True, default=uuid.uuid4),
    Column(
        "tenant_id",
        UUID(as_uuid=False),
        ForeignKey("tenant.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "workspace_id",
        UUID(as_uuid=False),
        ForeignKey("workspace.id", ondelete="CASCADE"),
        nullable=False,
    ),
    # URL-friendly identifier. Unique within a workspace; route is
    # /dashboards/<slug>. Service layer enforces format + auto-derives
    # from name on create.
    Column("slug", String(255), nullable=False),
    Column("name", String(255), nullable=False),
    Column("description", Text, nullable=True),
    # New dashboards start as drafts (Library renders them in Drafts
    # section). Publish flips to ``published`` + sets published_at.
    Column(
        "status",
        PgEnum(
            DashboardStatusEnum,
            name="dashboard_status",
            values_callable=lambda enum: [e.value for e in enum],
        ),
        nullable=False,
        server_default=text("'draft'"),
    ),
    Column(
        "visibility",
        PgEnum(
            DashboardVisibilityEnum,
            name="dashboard_visibility",
            values_callable=lambda enum: [e.value for e in enum],
        ),
        nullable=False,
        server_default=text("'workspace_members'"),
    ),
    # Back-pointer to the build chat. 1:1. SET NULL because the chat
    # can be purged independently (compliance) — the dashboard widgets
    # are the source of truth, the chat is the build history.
    Column(
        "build_chat_id",
        UUID(as_uuid=False),
        ForeignKey("chat.id", ondelete="SET NULL"),
        nullable=True,
    ),
    # SET NULL on user deletion — keep the dashboard, lose attribution.
    Column(
        "owner_id",
        UUID(as_uuid=False),
        ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
    ),
    Column(
        "created_by",
        UUID(as_uuid=False),
        ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
    ),
    Column("published_at", TIMESTAMP(timezone=True), nullable=True),
    Column(
        "created_at",
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    ),
    Column(
        "updated_at",
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    ),

    # Library URL routing — /dashboards/<slug> per workspace.
    UniqueConstraint(
        "workspace_id",
        "slug",
        name="ux_dashboard_workspace_slug",
    ),
    # Library section filter — Drafts vs Published per workspace.
    Index(
        "ix_dashboard_workspace_status",
        "workspace_id",
        "status",
    ),
    # Tenant-scoped lookups (e.g. cross-workspace admin views).
    Index("ix_dashboard_tenant", "tenant_id"),
)


dashboard_widget = Table(
    "dashboard_widget",
    metadata,

    Column("id", UUID(as_uuid=False), primary_key=True, default=uuid.uuid4),
    Column(
        "dashboard_id",
        UUID(as_uuid=False),
        ForeignKey("dashboard.id", ondelete="CASCADE"),
        nullable=False,
    ),
    # 12-col grid position (locked Q1 in the DA-P3 design discussion).
    # x ∈ [0, 12), w ∈ [1, 12]; y unbounded above; h ∈ [1, 12]. Service
    # layer validates ranges + non-overlap.
    Column("position_x", Integer, nullable=False, server_default=text("0")),
    Column("position_y", Integer, nullable=False, server_default=text("0")),
    Column("position_w", Integer, nullable=False, server_default=text("4")),
    Column("position_h", Integer, nullable=False, server_default=text("2")),
    Column(
        "widget_type",
        PgEnum(
            DashboardWidgetTypeEnum,
            name="dashboard_widget_type",
            values_callable=lambda enum: [e.value for e in enum],
        ),
        nullable=False,
    ),
    Column("title", String(255), nullable=False),
    Column("description", Text, nullable=True),
    # data_binding: { connection_id, schema_name, sql, params? }
    # viz_spec: { chart_type, x_axis, y_axis, series?, format?, ... }
    # grounding_metadata: { tables[], columns[], curator, last_validated_at }
    # All JSONB so we can partial-update specific keys without
    # rewriting the blob and for fast JSONB-path queries.
    Column("data_binding", JSONB, nullable=False),
    Column("viz_spec", JSONB, nullable=False),
    Column("grounding_metadata", JSONB, nullable=True),
    # The build-chat message that proposed this widget. SET NULL on
    # message purge (compliance) — the widget itself is the ground
    # truth; chat history is the audit trail.
    Column(
        "created_by_message_id",
        UUID(as_uuid=False),
        ForeignKey("message.id", ondelete="SET NULL"),
        nullable=True,
    ),
    Column(
        "created_at",
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    ),
    Column(
        "updated_at",
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    ),

    # Canonical render-time query — every dashboard load hits this.
    Index("ix_dashboard_widget_dashboard", "dashboard_id"),
)


dashboard_link_token = Table(
    "dashboard_link_token",
    metadata,

    Column("id", UUID(as_uuid=False), primary_key=True, default=uuid.uuid4),
    Column(
        "dashboard_id",
        UUID(as_uuid=False),
        ForeignKey("dashboard.id", ondelete="CASCADE"),
        nullable=False,
    ),
    # SHA-256 of the URL-safe token, hex-encoded (64 chars). The
    # plaintext token materialises exactly once — in the response of
    # the mint endpoint. From there on the DB only ever sees the hash;
    # a DB read can confirm a presented token matches a stored row
    # but cannot reconstruct the token. Same pattern Stripe / GitHub
    # PATs use for API credential storage at rest.
    Column("token_hash", String(64), nullable=False),
    # First 8 chars of the URL-safe plaintext, kept in the clear for
    # human identification in the share dialog ("link · xK4f2nM9").
    # 8 chars of url-safe base64 ≈ 48 bits of identifier entropy —
    # plenty for distinguishing a curator's own links, and gives away
    # nothing usable about the full secret. Same idea as GitHub PAT
    # list views showing ``ghp_xxxxXXXX``.
    Column("token_short", String(12), nullable=False),
    Column("expires_at", TIMESTAMP(timezone=True), nullable=True),
    Column("revoked_at", TIMESTAMP(timezone=True), nullable=True),
    # WHO revoked it. NULL = un-revoked, or system-initiated revoke
    # (future bg-job sweeper). SET NULL on user delete so the audit
    # fact (this link was revoked at T) outlives the actor.
    Column(
        "revoked_by_user_id",
        UUID(as_uuid=False),
        ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
    ),
    Column(
        "created_by",
        UUID(as_uuid=False),
        ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
    ),
    # Bumped on every successful anonymous access — feeds the share
    # dialog's "viewed N times" caption and the audit log.
    Column(
        "accessed_count",
        Integer,
        nullable=False,
        server_default=text("0"),
    ),
    Column(
        "created_at",
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    ),

    # Temporal invariants. Cheap CHECK constraints that turn a class
    # of service-bug ("we wrote an already-expired row") into a
    # DB-level constraint error — production-grade defense-in-depth.
    CheckConstraint(
        "expires_at IS NULL OR expires_at > created_at",
        name="ck_dashboard_link_token_expires_after_created",
    ),
    CheckConstraint(
        "revoked_at IS NULL OR revoked_at >= created_at",
        name="ck_dashboard_link_token_revoked_after_created",
    ),

    # Public viewer lookup — UNIQUE on the HASH. Hash collisions for
    # SHA-256 are cryptographically improbable, but UNIQUE makes the
    # invariant explicit at the schema level and the resolve path
    # depends on it (single-row read on hash match).
    Index(
        "ux_dashboard_link_token_token_hash",
        "token_hash",
        unique=True,
    ),
    # Active-link partial index. The query that powers the Library's
    # "Shared · N" pill JOIN is:
    #
    #     ... WHERE revoked_at IS NULL
    #             AND (expires_at IS NULL OR expires_at > now())
    #
    # Postgres won't accept ``now()`` (STABLE, not IMMUTABLE) inside
    # an index predicate, so the index filters on the immutable half
    # only (``revoked_at IS NULL``) and the query layer applies the
    # ``expires_at`` residual at scan time. Standard share-link
    # pattern — Stripe API keys + GitHub PATs index this way.
    # Replaces the v1 ``ix_dashboard_link_token_dashboard`` which
    # covered every row including revoked ones.
    Index(
        "ix_dashboard_link_token_active",
        "dashboard_id",
        postgresql_where=text("revoked_at IS NULL"),
    ),
)

# ---------------------------------------------------------------------------
# integration — unified credential record (WF-VS1).
#
# ONE row per credential, shared across all three pillars (ES via the
# 'ingest' capability, DA via 'query', WF via 'act'). The Vault secret
# lives behind ``vault_secret_id`` — the row NEVER carries the secret.
#
# Established once at the tenant level (owner_kind='tenant', the
# corporate connector that workspaces enable) or owned by an individual
# (owner_kind='user', the personal tier). The CHECK constraint enforces
# the per-owner_kind invariant so a row can't be ambiguous about who
# owns it. ``identity_kind`` (orthogonal) records who the destination
# SaaS sees. See product-feature-roadmap/workflow-execution §5a, §9.
# ---------------------------------------------------------------------------

integration = Table(
    "integration",
    metadata,

    Column("id", UUID(as_uuid=False), primary_key=True, default=uuid.uuid4),
    Column(
        "tenant_id",
        UUID(as_uuid=False),
        ForeignKey("tenant.id", ondelete="CASCADE"),
        nullable=False,
    ),

    # Ownership tier. tenant → shared via enablement; user → personal.
    Column(
        "owner_kind",
        PgEnum(
            IntegrationOwnerKindEnum,
            name="integration_owner_kind",
            values_callable=lambda enum: [e.value for e in enum],
        ),
        nullable=False,
    ),
    # Set ONLY for owner_kind='user' (the personal owner). NULL for tenant.
    Column(
        "owner_user_id",
        UUID(as_uuid=False),
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=True,
    ),
    # Set ONLY for owner_kind='user' (the workspace the personal
    # integration is attached to). NULL for tenant integrations — they
    # aren't tied to one workspace; workspaces opt in via enablement.
    Column(
        "workspace_id",
        UUID(as_uuid=False),
        ForeignKey("workspace.id", ondelete="CASCADE"),
        nullable=True,
    ),

    Column("provider", String(64), nullable=False),
    Column("display_name", String(255), nullable=False),
    # Pointer into Vault. The credential itself never lives in this row.
    Column("vault_secret_id", String(512), nullable=False),

    # Who the destination SaaS sees when this credential is used.
    Column(
        "identity_kind",
        PgEnum(
            IntegrationIdentityKindEnum,
            name="integration_identity_kind",
            values_callable=lambda enum: [e.value for e in enum],
        ),
        nullable=False,
    ),
    Column("identity_label", String(255), nullable=True),

    Column(
        "auth_kind",
        PgEnum(
            IntegrationAuthKindEnum,
            name="integration_auth_kind",
            values_callable=lambda enum: [e.value for e in enum],
        ),
        nullable=False,
    ),
    # OAuth scopes actually granted (audit + capability derivation).
    Column("oauth_scopes_granted", ARRAY(Text), nullable=True),
    # e.g. Jira site URL — needed to build API calls for instance-scoped
    # providers.
    Column("instance_url", String(512), nullable=True),
    # Provider account identity (Slack team_id, Jira cloud_id, etc.).
    Column("external_account_id", String(255), nullable=True),
    Column("external_account_name", String(255), nullable=True),

    # The cross-pillar axis: which pillars may use this integration.
    # Subset of {'ingest','query','act'} (stored as text[] to stay open
    # to new capabilities without an enum migration).
    Column("capabilities", ARRAY(Text), nullable=False),

    Column(
        "status",
        PgEnum(
            IntegrationStatusEnum,
            name="integration_status",
            values_callable=lambda enum: [e.value for e in enum],
        ),
        nullable=False,
        server_default=text("'active'"),
    ),
    Column("last_verified_at", TIMESTAMP(timezone=True), nullable=True),
    # Provider-specific non-secret extras. App-level validation forbids
    # credential-shaped keys here.
    Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")),

    Column(
        "created_by",
        UUID(as_uuid=False),
        ForeignKey("user.id", ondelete="SET NULL"),
        nullable=False,
    ),
    Column("created_at", TIMESTAMP(timezone=True), server_default=func.now(), nullable=False),
    Column("updated_at", TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False),

    # The owner_kind invariant — a row can't be ambiguous about who owns it.
    CheckConstraint(
        "(owner_kind = 'tenant' AND owner_user_id IS NULL AND workspace_id IS NULL) "
        "OR (owner_kind = 'user' AND owner_user_id IS NOT NULL AND workspace_id IS NOT NULL)",
        name="ck_integration_owner_kind_invariant",
    ),
    # A tenant can't connect the same provider account twice.
    UniqueConstraint(
        "tenant_id",
        "provider",
        "external_account_id",
        name="ux_integration_tenant_provider_account",
    ),
    # "All integrations for tenant T of provider P" — the create/list path.
    Index("ix_integration_tenant_provider", "tenant_id", "provider"),
    # "My personal integrations" — the personal-tier list path.
    Index("ix_integration_owner_user", "owner_user_id"),
)


# ---------------------------------------------------------------------------
# integration_workspace_enablement — per-workspace opt-in (WF-VS1).
#
# A tenant integration is unusable by a workspace until an enablement
# row exists. Enablement scopes capabilities DOWN (a subset of the
# integration's capabilities — enforced in the service). Carries a
# per-workspace display-name override and independent lifecycle so one
# workspace can disable without affecting others.
# ---------------------------------------------------------------------------

integration_workspace_enablement = Table(
    "integration_workspace_enablement",
    metadata,

    Column("id", UUID(as_uuid=False), primary_key=True, default=uuid.uuid4),
    Column(
        "integration_id",
        UUID(as_uuid=False),
        ForeignKey("integration.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "workspace_id",
        UUID(as_uuid=False),
        ForeignKey("workspace.id", ondelete="CASCADE"),
        nullable=False,
    ),
    # Subset of integration.capabilities granted to this workspace.
    Column("capabilities_enabled", ARRAY(Text), nullable=False),
    Column("display_name_override", String(255), nullable=True),
    Column(
        "status",
        PgEnum(
            IntegrationEnablementStatusEnum,
            name="integration_enablement_status",
            values_callable=lambda enum: [e.value for e in enum],
        ),
        nullable=False,
        server_default=text("'active'"),
    ),
    Column(
        "enabled_by",
        UUID(as_uuid=False),
        ForeignKey("user.id", ondelete="SET NULL"),
        nullable=False,
    ),
    Column("enabled_at", TIMESTAMP(timezone=True), server_default=func.now(), nullable=False),

    # A workspace enables a given tenant integration at most once.
    UniqueConstraint(
        "integration_id",
        "workspace_id",
        name="ux_integration_enablement_integration_workspace",
    ),
    # "What's enabled in workspace W" — the workspace integrations page.
    Index("ix_integration_enablement_workspace", "workspace_id"),
)


# ---------------------------------------------------------------------------
# integration_member_grant — per-member ACL (WF-VS1).
#
# Same cardinality/shape as workspace_da_access_grant: a flat
# per-(member, integration, capability) grid with deny-wins-anywhere
# resolution applied in the service. Default for a member is no access
# (no row); admins bypass via the JWT projection. ``capability`` is
# stored as text (includes the '*' wildcard) to stay open as
# capabilities grow.
# ---------------------------------------------------------------------------

integration_member_grant = Table(
    "integration_member_grant",
    metadata,

    Column("id", UUID(as_uuid=False), primary_key=True, default=uuid.uuid4),
    Column(
        "workspace_id",
        UUID(as_uuid=False),
        ForeignKey("workspace.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "user_id",
        UUID(as_uuid=False),
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "integration_id",
        UUID(as_uuid=False),
        ForeignKey("integration.id", ondelete="CASCADE"),
        nullable=False,
    ),
    # 'ingest' | 'query' | 'act' | '*' (wildcard = all capabilities).
    Column("capability", String(32), nullable=False),
    Column(
        "effect",
        PgEnum(
            IntegrationGrantEffectEnum,
            name="integration_grant_effect",
            values_callable=lambda enum: [e.value for e in enum],
        ),
        nullable=False,
    ),
    Column(
        "created_by",
        UUID(as_uuid=False),
        ForeignKey("user.id", ondelete="SET NULL"),
        nullable=False,
    ),
    Column("created_at", TIMESTAMP(timezone=True), server_default=func.now(), nullable=False),

    # One effect per member per integration per capability.
    UniqueConstraint(
        "workspace_id",
        "user_id",
        "integration_id",
        "capability",
        name="ux_integration_member_grant_member_integration_cap",
    ),
    # "All grants for member B in workspace W" — member-summary view.
    Index("ix_integration_member_grant_workspace_user", "workspace_id", "user_id"),
    # "Who can use integration I" — the integration members drawer.
    Index("ix_integration_member_grant_integration", "integration_id"),
)


# ---------------------------------------------------------------------------
# workflow — workspace-scoped workflow definitions (WF-VS2).
#
# The Workflow Execution pillar's definition store: one row per workflow the
# low-code builder produces. ``graph`` (JSONB) holds the node/edge definition
# the GenericGraphWorkflow interprets; Temporal owns *execution* state (event
# histories), this table owns the *definition*. created_by is metadata, not
# ownership — a workflow is workspace-owned and outlives its author, so the FK
# is SET NULL + nullable (unlike integration.created_by, which mismatches
# nullability and ondelete; tracked as TD-WF-INTEGRATION-CREATED-BY).
# ---------------------------------------------------------------------------

workflow = Table(
    "workflow",
    metadata,

    Column("id", UUID(as_uuid=False), primary_key=True, default=uuid.uuid4),
    Column(
        "tenant_id",
        UUID(as_uuid=False),
        ForeignKey("tenant.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "workspace_id",
        UUID(as_uuid=False),
        ForeignKey("workspace.id", ondelete="CASCADE"),
        nullable=False,
    ),

    Column("name", String(255), nullable=False),
    Column("description", Text, nullable=True),

    # The node/edge definition the GenericGraphWorkflow interprets.
    Column("graph", JSONB, nullable=False, server_default=text("'{}'::jsonb")),

    Column(
        "status",
        PgEnum(
            WorkflowStatusEnum,
            name="workflow_status",
            values_callable=lambda enum: [e.value for e in enum],
        ),
        nullable=False,
        server_default=text("'draft'"),
    ),

    Column(
        "created_by",
        UUID(as_uuid=False),
        ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
    ),
    Column("created_at", TIMESTAMP(timezone=True), server_default=func.now(), nullable=False),
    Column("updated_at", TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False),

    # "Workflows in workspace W of tenant T" — the builder list path.
    Index("ix_workflow_tenant_workspace", "tenant_id", "workspace_id"),
)
