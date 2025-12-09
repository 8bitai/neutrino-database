

from sqlalchemy import (
    Table, Column, Integer, String, Text, TIMESTAMP, Index, Float, ForeignKey, BigInteger, Enum as PgEnum
)
from sqlalchemy.dialects.postgresql import JSONB, UUID, ARRAY
from sqlalchemy.sql import func, text
from sqlalchemy import Boolean
from neutrino_database.models.base import metadata
from neutrino_database.models.enums import ConnectionStatus
import uuid


files = Table(
    "files",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("tenant_id", String, nullable=False),
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
    Column("tenant_id", String, nullable=False),
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
    Column("tenant_id", String, nullable=False),
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
    Column("tenant_id", String, nullable=False),
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
    Column("tenant_id", String, nullable=False),
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
    Column("tenant_id", String, nullable=False),
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
    Column("tenant_id", String, nullable=False),
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
    Column("tenant_id", String, nullable=False),
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
    Column("connector_type_id", String(100), ForeignKey("connector_types.id"), nullable=False),
    Column("status", PgEnum(ConnectionStatus), nullable=False, server_default=ConnectionStatus.active.name),
    Column("created_by", String(255)),
    Column("config_schema", Text),  # Tenant-specific configuration (e.g., SharePoint webUrl)
    Column("created_at", TIMESTAMP(timezone=True), server_default=func.now()),
    Column("updated_at", TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()),
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