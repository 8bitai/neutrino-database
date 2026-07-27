"""
Schema tests for the "no secrets in JSONB config" convention (VAPT D-6).

Several JSONB columns hold provider-specific *non-secret* configuration
(endpoints, model names, feature flags, …). The design intent, documented
inline in the schema, is that credential material NEVER lands in these
columns — secrets live in dedicated, encrypted columns
(e.g. ``providers.encrypted_value``, or a Vault secret referenced by id).

These tests mirror ``tests/test_pii_tagging.py``: they are pure
``tables.metadata`` assertions (no live DB needed), so they run in any
environment and fail loudly at review time if:

  * a config JSONB column is renamed / retyped out from under the convention,
  * a secret-shaped key is baked into a column's server-default, or
  * a JSONB column is itself named like a secret (inviting plaintext storage).

An optional live-data scan (``test_config_columns_hold_no_secret_keys_in_db``)
walks real rows when a test database is available; it is skipped otherwise.

"Secret-shaped" is a conservative name-pattern match — password, secret,
token, api_key, private_key, credential, access_key, client_secret, and
common variants. Better a false positive at review than a leaked key.
"""

from __future__ import annotations

import re

import pytest
from sqlalchemy.dialects.postgresql import JSONB

from neutrino_database.models import tables
from neutrino_database.models.credentials import api_keys  # noqa: F401  (registers `providers`)


# Curated inventory of JSONB columns that MUST stay free of secret material.
# (table_name, column_name). When a new non-secret config JSONB column is added,
# list it here so the convention is pinned and review-enforced.
NON_SECRET_CONFIG_JSONB_COLUMNS = [
    ("providers", "connection_config"),
    ("providers", "model_config"),
    ("integration", "metadata"),
    ("workflow_trigger", "config"),
]


# Conservative secret-shaped key-name matcher. Matches whole keys or embedded
# fragments (e.g. "openai_api_key", "clientSecret", "db_password").
_SECRET_KEY_RE = re.compile(
    r"(password|passwd|secret|api[_-]?key|access[_-]?key|"
    r"private[_-]?key|client[_-]?secret|credential|"
    r"auth[_-]?token|bearer|refresh[_-]?token)",
    re.IGNORECASE,
)


def find_secret_shaped_keys(value, _path: str = "") -> list[str]:
    """Recursively collect dotted paths of any dict key that looks like a secret.

    Reusable by services that want to enforce the same rule before persisting a
    config blob. Only *keys* are inspected — values are ignored (a value may
    legitimately contain the word "token"); a secret-shaped *key* is the signal.
    """
    hits: list[str] = []
    if isinstance(value, dict):
        for k, v in value.items():
            here = f"{_path}.{k}" if _path else str(k)
            if isinstance(k, str) and _SECRET_KEY_RE.search(k):
                hits.append(here)
            hits.extend(find_secret_shaped_keys(v, here))
    elif isinstance(value, (list, tuple)):
        for i, item in enumerate(value):
            hits.extend(find_secret_shaped_keys(item, f"{_path}[{i}]"))
    return hits


@pytest.mark.parametrize("table_name,column_name", NON_SECRET_CONFIG_JSONB_COLUMNS)
def test_config_column_exists_and_is_jsonb(table_name: str, column_name: str):
    """Pin each config column's identity + type. A rename or type change trips
    this test, forcing a re-review of the no-secrets convention."""
    table = tables.metadata.tables[table_name]
    assert column_name in table.c, (
        f"{table_name}.{column_name} is missing — update "
        f"NON_SECRET_CONFIG_JSONB_COLUMNS (VAPT D-6) if the schema changed."
    )
    col = table.c[column_name]
    assert isinstance(col.type, JSONB), (
        f"{table_name}.{column_name} is expected to be JSONB, got {col.type!r}."
    )


@pytest.mark.parametrize("table_name,column_name", NON_SECRET_CONFIG_JSONB_COLUMNS)
def test_config_column_server_default_has_no_secret_keys(
    table_name: str, column_name: str
):
    """A column's baked-in server default must not seed secret-shaped keys."""
    col = tables.metadata.tables[table_name].c[column_name]
    default = col.server_default
    default_sql = "" if default is None else str(getattr(default, "arg", default))
    offenders = [
        m.group(0) for m in _SECRET_KEY_RE.finditer(default_sql)
    ]
    assert not offenders, (
        f"{table_name}.{column_name} server default {default_sql!r} contains "
        f"secret-shaped key(s): {offenders}."
    )


def test_no_jsonb_column_is_named_like_a_secret():
    """Metadata-wide sweep: no JSONB column name itself looks like a secret.

    A JSONB column named e.g. ``credentials`` invites storing plaintext secret
    material as structured data — the schema should route secrets to dedicated
    encrypted columns instead."""
    offenders = []
    for table in tables.metadata.tables.values():
        for col in table.c:
            if isinstance(col.type, JSONB) and _SECRET_KEY_RE.search(col.name):
                offenders.append(f"{table.name}.{col.name}")
    assert not offenders, (
        "JSONB columns named like secrets (store secrets in a dedicated "
        f"encrypted column instead): {offenders}"
    )


def test_provider_secret_uses_dedicated_encrypted_column():
    """Convention anchor: ``providers`` keeps the actual secret in an encrypted
    TEXT column (``encrypted_value``), NOT in its JSONB config columns."""
    providers = tables.metadata.tables["providers"]
    assert "encrypted_value" in providers.c, (
        "providers.encrypted_value (the encrypted secret column) is missing — "
        "the no-secrets-in-JSONB convention relies on it."
    )


def test_find_secret_shaped_keys_helper():
    """Guard the helper itself so the convention's detector can't silently rot."""
    assert find_secret_shaped_keys({"endpoint": "x", "model": "y"}) == []
    assert find_secret_shaped_keys({"api_key": "sk-..."}) == ["api_key"]
    nested = {"auth": {"client_secret": "z"}, "opts": [{"password": "p"}]}
    found = find_secret_shaped_keys(nested)
    assert "auth.client_secret" in found
    assert "opts[0].password" in found


# ---------------------------------------------------------------------------
# Optional live-data scan — runs only when a real test DB is reachable.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_config_columns_hold_no_secret_keys_in_db(test_engine):
    """Walk real rows and assert no config JSONB blob has a secret-shaped key.

    Uses the session-scoped ``test_engine`` fixture (conftest). Skipped
    automatically when no test database is configured/reachable."""
    from sqlalchemy import select

    offenders: list[str] = []
    async with test_engine.connect() as conn:
        for table_name, column_name in NON_SECRET_CONFIG_JSONB_COLUMNS:
            table = tables.metadata.tables[table_name]
            col = table.c[column_name]
            result = await conn.execute(select(col))
            for (blob,) in result:
                for path in find_secret_shaped_keys(blob):
                    offenders.append(f"{table_name}.{column_name}:{path}")
    assert not offenders, f"secret-shaped keys found in JSONB config data: {offenders}"
