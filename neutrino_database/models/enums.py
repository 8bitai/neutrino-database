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

class MemberSourceEnum(str, Enum):
    """How we discovered this member"""
    SSO_LOGIN = "SSO_LOGIN"              # User logged in via UI/Teams
    FILE_PERMISSIONS = "FILE_PERMISSIONS"  # From file permission sync

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