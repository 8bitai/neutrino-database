"""
Schema tests for the PII tagging convention (NEU-1804 — folded into the
audit-log foundation slice as C3a's PII piece).

The convention: every column that holds personally-identifiable information
must declare ``comment='pii:<category>'`` at the SQLAlchemy ``Column``
level. The matching alembic migration mirrors those comments to the live
database via ``COMMENT ON COLUMN`` so the future C6 anonymization runner
can discover targets by reading ``pg_description``.

These tests pin v1 inventory: the five obvious PII columns we tag today,
plus the audit_log columns already tagged in C3a's first commit.

When a future slice adds a new PII column, the rule in
``our-engineering-standards.md`` §13 says to tag it at creation time.
The test list grows alongside; PR review enforces.

What "PII" means here, in plain language: anything that, on its own or
combined with another column, identifies a real human. Email, display
name, username, IP address, free-text input that may contain identifying
content. We tag conservatively — better to anonymize a borderline column
on erasure than miss one.

See ``user-stories/user-lifecycle.md`` § "PII inventory" for the
product-level catalogue and the per-tag anonymization replacements.
"""

from __future__ import annotations

import pytest

from neutrino_database.models import tables


# (table_name, column_name, expected_pii_tag)
#
# When you add a new PII-bearing column to tables.py, add it here too.
# The test below makes the failure obvious if you forget.
PII_COLUMNS = [
    # User identity
    ("user", "email", "pii:email"),
    ("user", "display_name", "pii:name"),
    ("user", "username", "pii:name"),
    # Workspace invitations carry the recipient's email + the inviter's
    # optional personal note (which may contain identifying content).
    ("workspace_invitation", "email", "pii:email"),
    ("workspace_invitation", "personal_message", "pii:freetext"),
    # Already tagged in C3a-base (audit_log table commit).
    ("audit_log", "ip_address", "pii:ipaddress"),
    ("audit_log", "user_agent", "pii:freetext"),
    # SSO/IdP membership record — email + display name are PII (VAPT D-7).
    ("member", "email", "pii:email"),
    ("member", "name", "pii:name"),
]


@pytest.mark.parametrize("table_name,column_name,expected_tag", PII_COLUMNS)
def test_pii_column_declares_correct_tag(
    table_name: str, column_name: str, expected_tag: str
):
    """Each known PII column must carry ``comment='pii:<category>'``
    on its SQLAlchemy ``Column`` declaration in ``tables.py``. The
    matching alembic migration applies the same comment to the live DB.

    SQLAlchemy's PostgreSQL dialect emits ``COMMENT ON COLUMN`` from
    the ``comment=`` kwarg automatically, so any column that's tagged
    here is also tagged on the test DB after ``Base.metadata.create_all``.
    """
    table = tables.metadata.tables[table_name]
    col = table.c[column_name]
    assert col.comment == expected_tag, (
        f"{table_name}.{column_name} must declare comment={expected_tag!r}. "
        f"Got {col.comment!r}. See our-engineering-standards.md §13 (PII tagging)."
    )


def test_pii_tag_format_is_valid_for_every_tagged_column():
    """Sanity check: every Column anywhere in the metadata that has a
    ``comment`` starting with ``pii:`` must use the documented format
    ``pii:<category>`` (single colon, snake_case category, no extra
    decoration). Catches typos and ill-formed tags.

    Future extension: ``pii:phi:<sub>`` for HIPAA-bound columns when we
    light up healthcare verticals. That's out of scope today; the
    pattern below allows it but doesn't require it.
    """
    import re
    pattern = re.compile(r"^pii(:[a-z][a-z0-9_]*)+$")
    offenders = []
    for table in tables.metadata.tables.values():
        for col in table.c:
            if col.comment and col.comment.startswith("pii"):
                if not pattern.match(col.comment):
                    offenders.append(f"{table.name}.{col.name}={col.comment!r}")
    assert not offenders, (
        "PII tag format violations (must match 'pii:<category>'): "
        + ", ".join(offenders)
    )
