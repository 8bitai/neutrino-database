from enum import Enum

from sqlalchemy import (
    Table, Column, Integer, String, Text, TIMESTAMP, Index, Float, ForeignKey, BigInteger, Enum as PgEnum,
    UniqueConstraint
)
from sqlalchemy.dialects.postgresql import JSONB, UUID, ARRAY
from sqlalchemy.sql import func, text
from sqlalchemy import Boolean
from neutrino_database.models.base import metadata

from neutrino_database.models.enums import ConnectionStatus, KeyStatusEnum, TenantStatusEnum, AllowedModuleEnum, \
    UserStatusEnum, IdpProviderEnum, MemberSourceEnum, MessageRoleEnum, WorkspaceStatusEnum, WorkspaceAccessStatusEnum

import uuid


files = Table(
    "files",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("tenant_id", String, ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
    Column("datasource_id", UUID(as_uuid=True), ForeignKey("datasources.id"), nullable=False),

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
    Column("tenant_id", String, ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
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
    Column("tenant_id", String, ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
    Column("file_id", UUID(as_uuid=True), ForeignKey("files.id", ondelete="CASCADE"), nullable=False),

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
    Column("tenant_id", String,ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
    Column("file_id", UUID(as_uuid=True), ForeignKey("files.id", ondelete="CASCADE"), nullable=False),

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
    Column("tenant_id", String, ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
    Column("file_id", UUID(as_uuid=True), ForeignKey("files.id", ondelete="CASCADE"), nullable=False),

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
    Column("tenant_id", String, ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
    Column("file_id", UUID(as_uuid=True), ForeignKey("files.id", ondelete="CASCADE"), nullable=False),
    Column("chunk_hash", String, nullable=False),

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
    Column("tenant_id", String, ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
    Column("file_id", UUID(as_uuid=True), ForeignKey("files.id", ondelete="CASCADE"), nullable=False),
    Column("chunk_id", UUID(as_uuid=True), ForeignKey("chunk.id", ondelete="CASCADE"), nullable=False),

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
    Column("tenant_id", String, ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
    Column("name", String, nullable=False),

    Column("strategy_id", UUID(as_uuid=True), nullable=True),
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
    Column("status", PgEnum(ConnectionStatus), nullable=False, server_default=ConnectionStatus.active.name),
    Column("created_by", String(255)),
    Column("config_schema", Text),  # Workspace-specific configuration (e.g., SharePoint webUrl)
    Column("created_at", TIMESTAMP(timezone=True), server_default=func.now()),
    Column("updated_at", TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()),

    Index("ix_connection_workspace", "workspace_id"),
    UniqueConstraint("workspace_id", "connector_type_id", name="ux_connection_workspace_connector_type"),
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

    UniqueConstraint("tenant_id", "email", name="ux_user_tenant_email"),
    Index("ix_user_tenant_status", "tenant_id", "status"),
    Index("ix_user_last_login_at", "last_login_at"),
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
)