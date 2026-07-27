"""VAPT D-7 — extend PII tagging to member + audit_log columns.

The PII tagging convention (``COMMENT ON COLUMN ... IS 'pii:<category>'``, see
``our-engineering-standards.md`` §13) drives the C6 GDPR-erasure anonymization
runner, which discovers targets by reading ``pg_description``. Untagged PII is a
hidden compliance gap.

The VAPT review flagged four columns as under-tagged relative to ``_PII_TAGS``:

  * ``member.email``          → pii:email     (was untagged)
  * ``member.name``           → pii:name      (was untagged)
  * ``audit_log.ip_address``  → pii:ipaddress (already tagged at table creation)
  * ``audit_log.user_agent``  → pii:freetext  (already tagged at table creation)

``member`` is the SSO/IdP membership record — email + display name are plainly
PII. The corresponding ``comment=`` tags have been added to ``tables.py`` so
``Base.metadata.create_all`` (the test path) tags them too, and
``tests/test_pii_tagging.py`` now pins them.

The two ``audit_log`` columns were already COMMENT-tagged in the migration that
created the table (``n1p2q3r4s5t6``); re-issuing the identical ``COMMENT ON
COLUMN`` here is idempotent (a no-op on envs that already have it) and makes the
tag set self-contained/auditable. It does NOT change their semantics.

Note: ``_PII_TAGS`` is a migration-local constant (it is not imported at
runtime anywhere — grep confirms only its own migration references it), so there
is no separate runtime source list to update. The runtime source of truth for
tags is the ``comment=`` kwargs on the ``Column`` objects in ``tables.py``.

Revision ID: a1c3e5b7d9f2
Revises: f2b4d6a8c1e3
Create Date: 2026-07-24
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "a1c3e5b7d9f2"
down_revision: Union[str, Sequence[str], None] = "f2b4d6a8c1e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (table, column, tag) — keep in lock-step with tests/test_pii_tagging.py.
# audit_log entries are re-asserted idempotently; member entries are new.
_PII_TAGS: list[tuple[str, str, str]] = [
    ("member", "email", "pii:email"),
    ("member", "name", "pii:name"),
    ("audit_log", "ip_address", "pii:ipaddress"),
    ("audit_log", "user_agent", "pii:freetext"),
]


def upgrade() -> None:
    for table, column, tag in _PII_TAGS:
        op.execute(f"COMMENT ON COLUMN {table}.{column} IS '{tag}'")


def downgrade() -> None:
    # Only clear the tags this migration introduced. The audit_log tags predate
    # this migration (set at table creation), so leave them in place on
    # downgrade rather than silently un-tagging live PII.
    for table, column, _tag in _PII_TAGS:
        if table == "member":
            op.execute(f"COMMENT ON COLUMN {table}.{column} IS NULL")
