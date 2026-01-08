from neutrino_database.models.enums import (
    KeyStatusEnum, TenantStatusEnum, UserStatusEnum, IdpProviderEnum,
    MemberSourceEnum, MessageRoleEnum, WorkspaceStatusEnum, WorkspaceAccessStatusEnum,
    RouterModeEnum, AgentMessageRole, RunStatus
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
    created_by: Mapped[Optional[str]]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
    deleted_at: Mapped[Optional[datetime]]

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