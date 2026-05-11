from neutrino_database.models.credentials.api_keys import providers
from neutrino_database.models.enums import (
    AgentMessageRole,
    DAConnectionStatusEnum,
    DADescriptionScopeEnum,
    DADescriptionSourceEnum,
    DAJoinHintSourceEnum,
    DAJoinTypeEnum,
    DAMetricSourceEnum,
    DASourceTypeEnum,
    DATableTypeEnum,
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
from neutrino_database.models import tables
from neutrino_database.models.base import Base
from datetime import datetime
from typing import Optional, List
from sqlalchemy.orm import Mapped, relationship


class LockLease(Base):
    """ORM wrapper for mutex_locks table"""
    __table__ = tables.lock_lease

    # Type hints
    name: Mapped[str]
    owner_id: Mapped[Optional[str]]
    lease_until: Mapped[Optional[datetime]]
    fencing_token: Mapped[int]


class RotationMutex(Base):
    """ORM wrapper for rotation_mutex table"""
    __table__ = tables.rotation_mutex

    # Type hints
    id: Mapped[bool]
    held_by: Mapped[Optional[str]]
    held_since: Mapped[Optional[datetime]]


class SigningKey(Base):
    """ORM wrapper for signing_keys table"""
    __table__ = tables.signing_key

    # Type hints
    kid: Mapped[str]
    public_pem: Mapped[str]
    private_pem: Mapped[str]
    status: Mapped[KeyStatusEnum]
    not_before: Mapped[Optional[datetime]]
    not_after: Mapped[Optional[datetime]]
    created_at: Mapped[datetime]


class TenantAuthzStore(Base):
    """ORM wrapper for tenant_authz_store table"""
    __table__ = tables.tenant_authz_store

    # Type hints
    id: Mapped[str]
    tenant_id: Mapped[str]
    store_id: Mapped[str]
    model_id: Mapped[str]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]

    # Relationship to Tenant
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="authz_store")


class Tenant(Base):
    """ORM wrapper for tenant table"""
    __table__ = tables.tenant

    # Type hints for all columns
    id: Mapped[str]
    name: Mapped[str]
    org_external_id: Mapped[str]
    status: Mapped[TenantStatusEnum]
    allowed_modules: Mapped[Optional[list]]
    status_updated_at: Mapped[Optional[datetime]]
    status_updated_by: Mapped[Optional[str]]
    status_reason: Mapped[Optional[str]]
    tenant_owner: Mapped[Optional[str]]
    onboarding_completed_at: Mapped[Optional[datetime]]
    max_workspaces: Mapped[int]
    allowed_invitation_domains: Mapped[List[str]]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
    deleted_at: Mapped[Optional[datetime]]

    # Relationships
    owner: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys="Tenant.tenant_owner",
        back_populates="owned_tenants"
    )

    authz_store: Mapped[Optional["TenantAuthzStore"]] = relationship(
        "TenantAuthzStore",
        back_populates="tenant",
        uselist=False,
        cascade="all, delete-orphan"
    )

    users: Mapped[List["User"]] = relationship(
        "User",
        foreign_keys="User.tenant_id",
        back_populates="tenant",
        cascade="all, delete-orphan",
        passive_deletes=True
    )

    roles: Mapped[List["Role"]] = relationship(
        "Role",
        back_populates="tenant",
        cascade="all, delete-orphan"
    )

    workspaces: Mapped[List["Workspace"]] = relationship(
        "Workspace",
        back_populates="tenant",
        cascade="all, delete-orphan",
        passive_deletes=True
    )

    invitations: Mapped[List["UserInvitation"]] = relationship(
        "UserInvitation",
        back_populates="tenant",
        cascade="all, delete-orphan"
    )

    identities: Mapped[List["TenantIdentity"]] = relationship(
        "TenantIdentity",
        back_populates="tenant",
        cascade="all, delete-orphan"
    )

    chats: Mapped[List["Chat"]] = relationship(
        "Chat",
        back_populates="tenant",
        cascade="all, delete-orphan",
        passive_deletes=True
    )

    messages: Mapped[List["Message"]] = relationship(
        "Message",
        back_populates="tenant",
        cascade="all, delete-orphan",
        passive_deletes=True
    )

    runs: Mapped[List["Run"]] = relationship(
        "Run",
        back_populates="tenant",
        cascade="all, delete-orphan",
        passive_deletes=True
    )


class User(Base):
    """ORM wrapper for user table"""
    __table__ = tables.user

    # Type hints for all columns
    id: Mapped[str]
    tenant_id: Mapped[str]
    email: Mapped[str]
    display_name: Mapped[Optional[str]]
    status: Mapped[UserStatusEnum]
    first_login_at: Mapped[Optional[datetime]]
    last_login_at: Mapped[Optional[datetime]]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
    deleted_at: Mapped[Optional[datetime]]
    default_workspace_id: Mapped[Optional[str]]
    username: Mapped[Optional[str]]
    password_hash: Mapped[Optional[str]]
    must_change_password: Mapped[bool]
    password_changed_at: Mapped[Optional[datetime]]
    # NEU-X8 — touched on promote / demote / transfer-accept; auth
    # middleware force-renews stale JWTs by comparing this against iat.
    permissions_changed_at: Mapped[Optional[datetime]]

    # Relationships
    tenant: Mapped["Tenant"] = relationship(
        "Tenant",
        foreign_keys="User.tenant_id",
        back_populates="users"
    )

    owned_tenants: Mapped[List["Tenant"]] = relationship(
        "Tenant",
        foreign_keys="Tenant.tenant_owner",
        back_populates="owner"
    )

    default_workspace: Mapped[Optional["Workspace"]] = relationship(
        "Workspace",
        foreign_keys="User.default_workspace_id",
        back_populates="default_for_users"
    )

    sso_identities: Mapped[List["SSOIdentity"]] = relationship(
        "SSOIdentity",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    members: Mapped[List["Member"]] = relationship(
        "Member",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    chats: Mapped[List["Chat"]] = relationship(
        "Chat",
        foreign_keys="Chat.created_by",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True
    )

    messages: Mapped[List["Message"]] = relationship(
        "Message",
        foreign_keys="Message.user_id",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True
    )

    invitations_sent: Mapped[List["UserInvitation"]] = relationship(
        "UserInvitation",
        foreign_keys="UserInvitation.inviter",
        back_populates="inviter_user",
        cascade="all, delete-orphan"
    )

    created_workspaces: Mapped[List["Workspace"]] = relationship(
        "Workspace",
        foreign_keys="Workspace.created_by",
        back_populates="creator"
    )

    workspace_memberships: Mapped[List["WorkspaceMember"]] = relationship(
        "WorkspaceMember",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    workspace_access_requests: Mapped[List["WorkspaceAccessRequest"]] = relationship(
        "WorkspaceAccessRequest",
        foreign_keys="WorkspaceAccessRequest.user_id",
        back_populates="user"
    )

    reviewed_access_requests: Mapped[List["WorkspaceAccessRequest"]] = relationship(
        "WorkspaceAccessRequest",
        foreign_keys="WorkspaceAccessRequest.reviewed_by",
        back_populates="reviewer"
    )

    workspace_invitations_sent: Mapped[List["WorkspaceInvitation"]] = relationship(
        "WorkspaceInvitation",
        foreign_keys="WorkspaceInvitation.inviter",
        back_populates="inviter_user"
    )

    runs: Mapped[List["Run"]] = relationship(
        "Run",
        foreign_keys="Run.user_id",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True
    )

    created_providers: Mapped[List["Provider"]] = relationship(
        "Provider",
        foreign_keys="Provider.created_by",
        back_populates="creator"
    )

class TenantIdentity(Base):
    """ORM wrapper for tenant_identity table"""
    __table__ = tables.tenant_identity

    # Type hints for all columns
    id: Mapped[str]
    tenant_id: Mapped[str]
    provider: Mapped[IdpProviderEnum]
    provider_org_id: Mapped[str]
    created_at: Mapped[datetime]

    # Relationships
    tenant: Mapped["Tenant"] = relationship(
        "Tenant",
        back_populates="identities"
    )


class SSOIdentity(Base):
    """ORM wrapper for sso_identity table"""
    __table__ = tables.sso_identity

    # Type hints for all columns
    id: Mapped[str]
    user_id: Mapped[str]
    provider: Mapped[IdpProviderEnum]
    provider_user_id: Mapped[str]
    provider_org_id: Mapped[str]
    last_login_at: Mapped[Optional[datetime]]
    raw_profile: Mapped[Optional[dict]]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]

    # Relationships
    user: Mapped["User"] = relationship(
        "User",
        back_populates="sso_identities"
    )


class Member(Base):
    """ORM wrapper for member table"""
    __table__ = tables.member

    # Type hints for all columns
    id: Mapped[str]
    user_id: Mapped[Optional[str]]
    email: Mapped[Optional[str]]
    name: Mapped[Optional[str]]
    provider: Mapped[IdpProviderEnum]
    provider_user_id: Mapped[str]
    provider_org_id: Mapped[str]
    source: Mapped[MemberSourceEnum]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]

    # Relationships
    user: Mapped[Optional["User"]] = relationship(
        "User",
        back_populates="members"
    )


class Role(Base):
    """ORM wrapper for role table"""
    __table__ = tables.role

    # Type hints for all columns
    id: Mapped[str]
    tenant_id: Mapped[str]
    key: Mapped[str]
    name: Mapped[str]
    description: Mapped[Optional[str]]

    # Relationships
    tenant: Mapped["Tenant"] = relationship(
        "Tenant",
        back_populates="roles"
    )


class AppPermission(Base):
    """ORM wrapper for app_permission table"""
    __table__ = tables.app_permission

    # Type hints for all columns
    id: Mapped[str]
    key: Mapped[str]
    name: Mapped[str]
    description: Mapped[Optional[str]]


class UserInvitation(Base):
    """ORM wrapper for user_invitation table"""
    __table__ = tables.user_invitation

    # Type hints for all columns
    id: Mapped[str]
    tenant_id: Mapped[str]
    inviter: Mapped[str]
    email: Mapped[str]
    expires_at: Mapped[datetime]
    accepted_at: Mapped[Optional[datetime]]
    deleted_at: Mapped[Optional[datetime]]
    created_at: Mapped[datetime]

    # Relationships
    tenant: Mapped["Tenant"] = relationship(
        "Tenant",
        back_populates="invitations"
    )

    inviter_user: Mapped["User"] = relationship(
        "User",
        foreign_keys="UserInvitation.inviter",
        back_populates="invitations_sent"
    )


class Chat(Base):
    """ORM wrapper for chat table"""
    __table__ = tables.chat

    # Type hints for all columns
    id: Mapped[str]
    tenant_id: Mapped[str]
    created_by: Mapped[Optional[str]]
    title: Mapped[Optional[str]]
    incognito: Mapped[bool]
    pinned: Mapped[bool]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
    deleted_at: Mapped[Optional[datetime]]

    # Relationships
    tenant: Mapped["Tenant"] = relationship(
        "Tenant",
        back_populates="chats"
    )

    user: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys="Chat.created_by",
        back_populates="chats"
    )

    messages: Mapped[List["Message"]] = relationship(
        "Message",
        back_populates="chat",
        cascade="all, delete-orphan",
        order_by="Message.created_at"
    )

    runs: Mapped[List["Run"]] = relationship(
        "Run",
        foreign_keys="Run.session_id",
        back_populates="chat",
        cascade="all, delete-orphan"
    )


class Message(Base):
    """ORM wrapper for message table"""
    __table__ = tables.message

    # Type hints for all columns
    id: Mapped[str]
    tenant_id: Mapped[str]
    chat_id: Mapped[str]
    user_id: Mapped[Optional[str]]
    role: Mapped[MessageRoleEnum]
    content: Mapped[str]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
    deleted_at: Mapped[Optional[datetime]]

    # Relationships
    tenant: Mapped["Tenant"] = relationship(
        "Tenant",
        back_populates="messages"
    )

    chat: Mapped["Chat"] = relationship(
        "Chat",
        back_populates="messages"
    )

    user: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys="Message.user_id",
        back_populates="messages"
    )

    runs: Mapped[List["Run"]] = relationship(
        "Run",
        back_populates="message",
        cascade="all, delete-orphan"
    )

class Workspace(Base):
    """ORM wrapper for workspace table"""
    __table__ = tables.workspace

    # Type hints for all columns
    id: Mapped[str]
    tenant_id: Mapped[str]
    name: Mapped[str]
    description: Mapped[Optional[str]]
    status: Mapped[WorkspaceStatusEnum]
    enabled_pillars: Mapped[List[PillarEnum]]
    created_by: Mapped[Optional[str]]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
    deleted_at: Mapped[Optional[datetime]]
    deletion_scheduled_for: Mapped[Optional[datetime]]
    deletion_initiated_by: Mapped[Optional[str]]

    # Relationships
    tenant: Mapped["Tenant"] = relationship(
        "Tenant",
        back_populates="workspaces"
    )

    creator: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys="Workspace.created_by",
        back_populates="created_workspaces"
    )

    default_for_users: Mapped[List["User"]] = relationship(
        "User",
        foreign_keys="User.default_workspace_id",
        back_populates="default_workspace"
    )

    members: Mapped[List["WorkspaceMember"]] = relationship(
        "WorkspaceMember",
        back_populates="workspace",
        cascade="all, delete-orphan"
    )

    access_requests: Mapped[List["WorkspaceAccessRequest"]] = relationship(
        "WorkspaceAccessRequest",
        foreign_keys="WorkspaceAccessRequest.workspace_id",
        back_populates="workspace",
        cascade="all, delete-orphan"
    )

    invitations: Mapped[List["WorkspaceInvitation"]] = relationship(
        "WorkspaceInvitation",
        back_populates="workspace",
        cascade="all, delete-orphan"
    )

    orchestrator_config: Mapped[Optional["OrchestratorConfig"]] = relationship(
        "OrchestratorConfig",
        back_populates="workspace",
        uselist=False,
        cascade="all, delete-orphan"
    )

    runs: Mapped[List["Run"]] = relationship(
        "Run",
        back_populates="workspace",
        cascade="all, delete-orphan",
        passive_deletes=True
    )

    providers: Mapped[List["Provider"]] = relationship(
        "Provider",
        back_populates="workspace",
        cascade="all, delete-orphan"
    )


class WorkspaceMember(Base):
    """ORM wrapper for workspace_member table"""
    __table__ = tables.workspace_member

    # Type hints for all columns
    id: Mapped[str]
    workspace_id: Mapped[str]
    user_id: Mapped[str]
    is_workspace_admin: Mapped[bool]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
    first_visited_at: Mapped[Optional[datetime]]

    # Relationships
    workspace: Mapped["Workspace"] = relationship(
        "Workspace",
        back_populates="members"
    )

    user: Mapped["User"] = relationship(
        "User",
        back_populates="workspace_memberships"
    )


class WorkspaceAccessRequest(Base):
    """ORM wrapper for workspace_access_request table"""
    __table__ = tables.workspace_access_request

    # Type hints for all columns
    id: Mapped[str]
    workspace_id: Mapped[str]
    user_id: Mapped[str]
    status: Mapped[WorkspaceAccessStatusEnum]
    requested_at: Mapped[datetime]
    reviewed_by: Mapped[Optional[str]]
    reviewed_at: Mapped[Optional[datetime]]
    review_note: Mapped[Optional[str]]

    # Relationships
    workspace: Mapped["Workspace"] = relationship(
        "Workspace",
        foreign_keys="WorkspaceAccessRequest.workspace_id",
        back_populates="access_requests"
    )

    user: Mapped["User"] = relationship(
        "User",
        foreign_keys="WorkspaceAccessRequest.user_id",
        back_populates="workspace_access_requests"
    )

    reviewer: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys="WorkspaceAccessRequest.reviewed_by",
        back_populates="reviewed_access_requests"
    )


class WorkspaceInvitation(Base):
    """ORM wrapper for workspace_invitation table"""
    __table__ = tables.workspace_invitation

    # Type hints for all columns
    id: Mapped[str]
    workspace_id: Mapped[str]
    inviter: Mapped[str]
    email: Mapped[str]
    is_workspace_admin: Mapped[bool]
    personal_message: Mapped[Optional[str]]
    expires_at: Mapped[datetime]
    accepted_at: Mapped[Optional[datetime]]
    deleted_at: Mapped[Optional[datetime]]
    created_at: Mapped[datetime]

    # Relationships
    workspace: Mapped["Workspace"] = relationship(
        "Workspace",
        back_populates="invitations"
    )

    inviter_user: Mapped["User"] = relationship(
        "User",
        foreign_keys="WorkspaceInvitation.inviter",
        back_populates="workspace_invitations_sent"
    )


class OrchestratorConfig(Base):
    """ORM wrapper for orchestrator_config table"""
    __table__ = tables.orchestrator_config

    # Type hints for all columns
    id: Mapped[str]
    workspace_id: Mapped[str]
    router_mode: Mapped[RouterModeEnum]
    router_classification_prompt: Mapped[Optional[str]]
    response_synthesis_prompt: Mapped[Optional[str]]
    retrieval_strategy: Mapped[RetrievalStrategyEnum]
    retrieval_config: Mapped[dict]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]

    # Relationships
    workspace: Mapped["Workspace"] = relationship(
        "Workspace",
        back_populates="orchestrator_config"
    )

class Run(Base):
    """Top level run record for each agent request."""
    __table__ = tables.runs

    # Type hints for all columns
    id: Mapped[str]
    message_id: Mapped[str]
    session_id: Mapped[Optional[str]]
    tenant_id: Mapped[str]
    workspace_id: Mapped[str]
    user_id: Mapped[Optional[str]]
    status: Mapped[RunStatus]
    input_message: Mapped[str]
    final_answer: Mapped[Optional[str]]
    sources: Mapped[Optional[dict]]
    flow_run_id: Mapped[Optional[str]]
    waiting_instance_id: Mapped[Optional[str]]
    input_request: Mapped[Optional[dict]]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]

    # Relationships
    message: Mapped["Message"] = relationship(
        "Message",
        foreign_keys="Run.message_id",
        back_populates="runs"
    )

    chat: Mapped[Optional["Chat"]] = relationship(
        "Chat",
        foreign_keys="Run.session_id",
        back_populates="runs"
    )

    tenant: Mapped["Tenant"] = relationship(
        "Tenant",
        foreign_keys="Run.tenant_id",
        back_populates="runs"
    )

    workspace: Mapped["Workspace"] = relationship(
        "Workspace",
        foreign_keys="Run.workspace_id",
        back_populates="runs"
    )

    user: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys="Run.user_id",
        back_populates="runs"
    )

    conversations: Mapped[List["ReactConversation"]] = relationship(
        "ReactConversation",
        back_populates="run",
        cascade="all, delete-orphan"
    )

    events: Mapped[List["RunEvent"]] = relationship(
        "RunEvent",
        back_populates="run",
        cascade="all, delete-orphan"
    )

    trace_spans: Mapped[List["TraceSpan"]] = relationship(
        "TraceSpan",
        back_populates="run",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ReactConversation(Base):
    """ReAct messages within a run, supports delegation levels."""
    __table__ = tables.react_conversations

    # Type hints for all columns
    id: Mapped[str]
    run_id: Mapped[str]
    instance_id: Mapped[Optional[str]]
    delegation_level: Mapped[int]
    agent_name: Mapped[str]
    role: Mapped[AgentMessageRole]
    content: Mapped[str]
    tool_name: Mapped[Optional[str]]
    tool_params: Mapped[Optional[dict]]
    created_at: Mapped[datetime]

    # Relationships
    run: Mapped["Run"] = relationship(
        "Run",
        back_populates="conversations"
    )


class RunEvent(Base):
    """Events for SSE streaming and audit trail."""
    __table__ = tables.run_events

    # Type hints for all columns
    id: Mapped[str]
    run_id: Mapped[str]
    sequence: Mapped[int]
    event_type: Mapped[str]
    agent_name: Mapped[Optional[str]]
    instance_id: Mapped[Optional[str]]
    data: Mapped[Optional[dict]]
    created_at: Mapped[datetime]

    # Relationships
    run: Mapped["Run"] = relationship(
        "Run",
        back_populates="events"
    )

class TraceSpan(Base):
    """Observability span for LLM calls, tool calls, and agent runs."""
    __table__ = tables.trace_spans

    id: Mapped[str]
    run_id: Mapped[str]
    parent_span_id: Mapped[Optional[str]]
    sequence: Mapped[int]
    span_type: Mapped[SpanType]
    name: Mapped[str]
    agent_name: Mapped[Optional[str]]
    status: Mapped[SpanStatus]
    started_at: Mapped[datetime]
    ended_at: Mapped[datetime]
    latency_ms: Mapped[int]
    attributes: Mapped[Optional[dict]]
    created_at: Mapped[datetime]

    run: Mapped["Run"] = relationship(
        "Run",
        back_populates="trace_spans",
    )


class ExcelDataset(Base):
    """Uploaded Excel dataset tracked for text-to-SQL."""
    __table__ = tables.excel_datasets

    id: Mapped[str]
    workspace_id: Mapped[str]
    tenant_id: Mapped[str]
    uploaded_by: Mapped[Optional[str]]
    original_filename: Mapped[str]
    schema_name: Mapped[str]
    minio_path: Mapped[str]
    status: Mapped[ExcelDatasetStatus]
    table_metadata: Mapped[Optional[dict]]
    file_size_bytes: Mapped[int]
    error_details: Mapped[Optional[str]]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]

    workspace: Mapped["Workspace"] = relationship(
        "Workspace",
        foreign_keys="ExcelDataset.workspace_id",
    )

    tenant: Mapped["Tenant"] = relationship(
        "Tenant",
        foreign_keys="ExcelDataset.tenant_id",
    )

    uploader: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys="ExcelDataset.uploaded_by",
    )


class Provider(Base):  # ← Singular, not Providers
    """ORM wrapper for providers table"""
    __table__ = providers

    id: Mapped[str]
    workspace_id: Mapped[str]
    provider_category: Mapped[str]  # ← ADD THIS NEW FIELD
    service_type: Mapped[str]
    display_name: Mapped[str]
    encrypted_value: Mapped[str]
    encryption_method: Mapped[str]
    connection_config: Mapped[Optional[dict]]  # ← Make Optional
    model_config: Mapped[Optional[dict]]  # ← Make Optional
    is_active: Mapped[bool]
    is_deleted: Mapped[bool]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
    created_by: Mapped[Optional[str]]

    # Relationships
    workspace: Mapped["Workspace"] = relationship(
        "Workspace",
        back_populates="providers"
    )

    creator: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys="Provider.created_by",  # ← Changed from LLMProvider
        back_populates="created_providers"  # ← Changed from created_llm_providers
    )


class AuditLog(Base):
    """ORM wrapper for audit_log — append-only compliance event store.

    UPDATE and DELETE on this table raise SQLSTATE AU001 via the
    audit_log_immutability Postgres trigger (installed in tables.py).
    Use INSERT only.

    See user-stories/user-lifecycle.md § "Audit log requirements".
    """
    __table__ = tables.audit_log

    id: Mapped[str]
    tenant_id: Mapped[str]
    actor_user_id: Mapped[Optional[str]]
    event_type: Mapped[str]
    resource_type: Mapped[str]
    resource_id: Mapped[str]
    event_metadata: Mapped[dict]
    ip_address: Mapped[Optional[str]]
    user_agent: Mapped[Optional[str]]
    occurred_at: Mapped[datetime]


class TenancyOwnershipTransfer(Base):
    """ORM wrapper for tenancy_ownership_transfer (NEU-X3).

    A pending row exists from the moment the Owner clicks "Transfer
    ownership" until the target accepts, the Owner cancels, the
    7-day window expires, or the retention runner sweeps the row.
    Only one pending row per tenant at any time (partial unique
    index in tables.py).

    See user-stories/tenant-admin-actions.md § 4 (Primary Ownership
    transfer) for the lifecycle.
    """

    __table__ = tables.tenancy_ownership_transfer

    id: Mapped[str]
    tenant_id: Mapped[str]
    from_user_id: Mapped[Optional[str]]
    to_user_id: Mapped[Optional[str]]
    token: Mapped[str]
    expires_at: Mapped[datetime]
    accepted_at: Mapped[Optional[datetime]]
    cancelled_at: Mapped[Optional[datetime]]
    created_at: Mapped[datetime]


# ===========================================================================
# Data Analytics — ORM wrappers (NEU-1811 DA-P0).
#
# Seven tables encoding the DA pillar's per-warehouse curated state. See
# tables.py for the canonical schema and the inline service-ownership
# comment block (feature.md F4). Pydantic boundary models live alongside
# in da_schemas.py — these ORM classes are for SQLAlchemy session use
# (filters, inserts, joins) inside connector-service and agent-platform.
# ===========================================================================


class DAConnection(Base):
    """Tenant-level DA Connection — one row per tenant warehouse credential.

    Lifecycle CRUD owned by connector-service (feature.md F4). agent-platform
    reads it to know which connection to call when running metadata sync /
    SQL execution against the warehouse.
    """

    __table__ = tables.da_connection

    id: Mapped[str]
    tenant_id: Mapped[str]
    source_type: Mapped[DASourceTypeEnum]
    connection_name: Mapped[str]
    credentials: Mapped[dict]  # KMS-wrapped JSONB
    status: Mapped[DAConnectionStatusEnum]
    created_by: Mapped[Optional[str]]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


class WorkspaceMetadataConnection(Base):
    """Workspace's curated view of one schema within a tenant Connection.

    One row per (workspace_id, connection_id, database_name, schema_name).
    Denormalises ``source_type`` + ``connection_name`` from da_connection
    so display + routing reads don't need a join.
    """

    __table__ = tables.workspace_metadata_connection

    id: Mapped[str]
    workspace_id: Mapped[str]
    connection_id: Mapped[str]
    source_type: Mapped[DASourceTypeEnum]
    connection_name: Mapped[str]
    database_name: Mapped[str]
    schema_name: Mapped[str]
    schema_description: Mapped[Optional[str]]
    last_synced_at: Mapped[Optional[datetime]]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


class WorkspaceMetadataTable(Base):
    """Curated table within a workspace's curated schema.

    Holds DDL (Phase 1 light pull) + descriptions (3-source precedence:
    admin_seed > ai_generated > native_comment) + curation flags.
    """

    __table__ = tables.workspace_metadata_table

    id: Mapped[str]
    workspace_metadata_connection_id: Mapped[str]
    table_name: Mapped[str]
    table_type: Mapped[DATableTypeEnum]
    native_comment: Mapped[Optional[str]]
    row_count: Mapped[Optional[int]]
    table_logical_name: Mapped[Optional[str]]
    admin_seed_description: Mapped[Optional[str]]
    ai_generated_description: Mapped[Optional[str]]
    is_included: Mapped[bool]
    is_archived: Mapped[bool]
    last_enriched_at: Mapped[Optional[datetime]]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


class WorkspaceMetadataColumn(Base):
    """Curated column within a curated table.

    Carries DDL + descriptions + privacy flags + Phase-2 enrichments
    (samples / cardinality / stats) + semantic fields
    (synonyms / unit / format_hint / valid_aggregations).
    Synonyms (Entity 7) are nested as a JSONB list on this row.
    """

    __table__ = tables.workspace_metadata_column

    id: Mapped[str]
    workspace_metadata_table_id: Mapped[str]
    column_name: Mapped[str]
    data_type: Mapped[str]
    nullable: Mapped[bool]
    is_primary_key: Mapped[bool]
    is_foreign_key: Mapped[bool]
    foreign_key_to: Mapped[Optional[list]]
    native_comment: Mapped[Optional[str]]
    ordinal_position: Mapped[int]
    column_logical_name: Mapped[Optional[str]]
    admin_seed_description: Mapped[Optional[str]]
    ai_generated_description: Mapped[Optional[str]]
    is_pii: Mapped[bool]
    is_restricted: Mapped[bool]
    allow_sample_values: Mapped[bool]
    sample_values: Mapped[Optional[list]]
    cardinality_score: Mapped[Optional[float]]
    statistical_profile: Mapped[Optional[dict]]
    synonyms: Mapped[Optional[list]]
    unit: Mapped[Optional[str]]
    format_hint: Mapped[Optional[str]]
    valid_aggregations: Mapped[Optional[list]]
    is_included: Mapped[bool]
    is_archived: Mapped[bool]
    last_enriched_at: Mapped[Optional[datetime]]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


class Metric(Base):
    """Workspace-scoped business metric.

    HITL lifecycle: AI suggestions land with ``accepted=false`` until an
    admin accepts. Partial unique on (workspace_id, name) WHERE not
    archived — archiving a metric frees its name for reuse.
    """

    __table__ = tables.metric

    id: Mapped[str]
    workspace_id: Mapped[str]
    name: Mapped[str]
    description: Mapped[Optional[str]]
    sql_expression: Mapped[str]
    filters: Mapped[Optional[str]]
    applicable_tables: Mapped[list]
    valid_dimensions: Mapped[Optional[list]]
    source: Mapped[DAMetricSourceEnum]
    accepted: Mapped[bool]
    created_by: Mapped[Optional[str]]
    updated_by: Mapped[Optional[str]]
    last_used_at: Mapped[Optional[datetime]]
    is_archived: Mapped[bool]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


class JoinHint(Base):
    """Workspace-scoped join hint between two curated tables.

    Cascades when either side table is removed (the hint becomes
    meaningless). HITL: AI-suggested hints land with ``accepted=false``.
    """

    __table__ = tables.join_hint

    id: Mapped[str]
    workspace_id: Mapped[str]
    left_table_id: Mapped[str]
    left_columns: Mapped[list]
    right_table_id: Mapped[str]
    right_columns: Mapped[list]
    join_type: Mapped[DAJoinTypeEnum]
    semantic_description: Mapped[Optional[str]]
    source: Mapped[DAJoinHintSourceEnum]
    accepted: Mapped[bool]
    created_by: Mapped[Optional[str]]
    is_archived: Mapped[bool]
    created_at: Mapped[datetime]


class DescriptionVersion(Base):
    """Append-only version history for descriptions across 4 scopes.

    Soft-FK pattern: ``parent_id`` points at one of
    ``workspace_metadata_table`` / ``workspace_metadata_column`` /
    ``metric`` / ``join_hint`` — discriminated by ``scope``. Service layer
    enforces parent_id matches the scope.

    No ``updated_at`` — corrections are new versions, not in-place edits.
    """

    __table__ = tables.description_version

    id: Mapped[str]
    scope: Mapped[DADescriptionScopeEnum]
    parent_id: Mapped[str]
    version_number: Mapped[int]
    source: Mapped[DADescriptionSourceEnum]
    content: Mapped[str]
    generated_at: Mapped[datetime]
    generated_by: Mapped[Optional[str]]
    inputs_snapshot: Mapped[Optional[dict]]