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
