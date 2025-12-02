from enum import Enum


class ConnectionStatus(str, Enum):
    active = "active"
    error = "error"
    revoked = "revoked"

