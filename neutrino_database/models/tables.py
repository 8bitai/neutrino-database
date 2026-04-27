from sqlalchemy import (
    Table, Column, Integer, String, Text, TIMESTAMP, Index, Float, ForeignKey, BigInteger, Enum as PgEnum,
    UniqueConstraint, Numeric
)
from sqlalchemy.dialects.postgresql import JSONB, UUID, ARRAY
from sqlalchemy.sql import func, text
from sqlalchemy import Boolean
from neutrino_database.models.base import metadata

from neutrino_database.models.enums import (
    AgentMessageRole,
    AllowedModuleEnum,
    ConnectionStatus,
    ExcelDatasetStatus,
    IdpProviderEnum,
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

    # status
    Column("status", String(50), nullable=False, server_default=text("'DOWNLOADED'")),

    # Timestamps
    Column("created_at", TIMESTAMP(timezone=True), server_default=func.now(), nullable=False),
    Column("updated_at", TIMESTAMP(timezone=True), server_default=func.now(), nullable=False, onupdate=func.now()),

    Column("created_by", String, nullable=False),
    Column("is_deleted", Boolean, nullable=False, server_default=text("false")),

    Column("permission_mirroring_status", String(50), nullable=False, server_default=text("'NOT INITIATED'")),
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
    Column("email", String(320), nullable=False),
    Column("display_name", String(255), nullable=True),
    Column("status", PgEnum(UserStatusEnum, name="user_status"), nullable=False, default=UserStatusEnum.ACTIVE),
    Column("first_login_at", TIMESTAMP(timezone=True), nullable=True),
    Column("last_login_at", TIMESTAMP(timezone=True), nullable=True),
    Column("created_at", TIMESTAMP(timezone=True), server_default=func.now(), nullable=False),
    Column("updated_at", TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False),
    Column("deleted_at", TIMESTAMP(timezone=True), nullable=True),
    Column("default_workspace_id", UUID(as_uuid=False), ForeignKey("workspace.id", ondelete="SET NULL"), nullable=True),

    # Local auth columns — nullable so SSO-only users are unaffected
    Column("username", String(100), nullable=True),
    Column("password_hash", Text, nullable=True),
    Column("must_change_password", Boolean, nullable=False, server_default="false"),
    Column("password_changed_at", TIMESTAMP(timezone=True), nullable=True),

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
    Column("created_by", UUID(as_uuid=False), ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
    Column("title", String(255), nullable=True),
    Column("incognito", Boolean, nullable=False, server_default=text("false")),
    Column("pinned", Boolean, nullable=False, server_default=text("false")),
    Column("created_at", TIMESTAMP(timezone=True), server_default=func.now(), nullable=False),
    Column("updated_at", TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False),
    Column("deleted_at", TIMESTAMP(timezone=True), nullable=True),

    Index("ix_chat_tenant_incognito", "tenant_id", "incognito"),
    Index("ix_chat_tenant_non_incognito", "tenant_id", postgresql_where=text("incognito = false")),
    Index("ix_chat_tenant_updated_at", "tenant_id", "updated_at"),
    Index("ix_chat_created_by", "tenant_id", "created_by"),
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

    UniqueConstraint("tenant_id", "name", name="ux_workspace_tenant_name"),
    Index("ix_workspace_tenant", "tenant_id"),
    Index("ix_workspace_tenant_status", "tenant_id", "status"),
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
    Column("email", String(320), nullable=False),
    Column("is_workspace_admin", Boolean, nullable=False, server_default=text("false")),
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