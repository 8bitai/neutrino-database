"""[NEU-1816] CANON-DOC-1 — files table gains the CanonicalDocument shape.

Pins the schema contract for the unified canonical document model (see
`product-feature-roadmap/enterprise-search/unified-doc-parse-chunk.md`)
which makes the same row in `files` capable of representing both
file-source connectors (SharePoint, OneDrive, Drive — bytes) AND
record-source connectors (Jira, Confluence, Slack, Linear — JSON
records that have no bytes).

Before this slice, `files` carried `original_filename`/`file_type`/
`file_size_bytes`/`file_sha256` as NOT NULL — file-only assumptions
baked into the schema. Jira issues do not have any of those.

This slice:
  1. Adds the CanonicalDocument fields:
       source_type, source_url, container_id, container_name, breadcrumb,
       language, parent_doc_id, facets, display_metadata, title,
       viewers, acl_extractor_version, acl_extracted_at
  2. Relaxes file-only columns to nullable (records leave them NULL).
  3. Introduces the `file_source_type` enum with the 12 canonical
     source kinds (see `unified-doc-parse-chunk.md` "Source_type —
     closed vocabulary").
  4. Adds the parent_doc_id self-FK with ON DELETE CASCADE so
     comments/replies/attachments cascade when their parent issue or
     thread is removed.

Pre-production (per [[project_pre_production_no_real_users]]) — no
backfill. Existing rows backfill `source_type='file'` from the migration
itself (every legacy row WAS a file); new ingest writes set source_type
explicitly.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa


_CANONICAL_SOURCE_TYPES = (
    "file",
    "issue",
    "pull_request",
    "commit",
    "page",
    "record",
    "message",
    "email",
    "event",
    "comment",
    "attachment",
    "ticket",
)


_NEW_COLUMNS = {
    # name              nullable   notes
    "source_type":      False,     # ENUM file_source_type — every doc has one
    "source_url":       False,     # every doc has a clickable link
    "container_id":     False,     # drive id / project key / space key / channel id
    "container_name":   False,     # human-readable container ("Engineering Wiki")
    "breadcrumb":       True,      # JSONB array; nullable for empty
    "language":         True,      # ISO code; nullable when undetected
    "parent_doc_id":    True,      # self-FK for comments / replies / attachments
    "facets":           False,     # JSONB; defaults to {} — filterable keyword bag
    "display_metadata": False,     # JSONB; defaults to {} — display-only bag
                                   # (renamed from "metadata" to avoid the
                                   # SQLAlchemy MetaData reserved word)
    "title":            True,      # human title; nullable for messages/commits
    "viewers":          False,     # JSONB; defaults to {} — the ViewerSet payload
    "acl_extractor_version": True, # bump on extractor changes → re-resolve
    "acl_extracted_at": True,      # populated when ACL is resolved
}


_RELAXED_TO_NULLABLE = (
    # Were NOT NULL pre-CANON-DOC-1; become nullable so record-source
    # connectors (Jira, Confluence, Slack) can leave them unset.
    "original_filename",
    "file_type",
    "storage_uri",
    "file_size_bytes",
    "file_sha256",
)


async def _columns(test_engine, table_name: str) -> dict:
    async with test_engine.connect() as conn:
        return await conn.run_sync(
            lambda sync_conn: {
                c["name"]: c
                for c in sa.inspect(sync_conn).get_columns(table_name)
            }
        )


async def _foreign_keys(test_engine, table_name: str) -> list[dict]:
    async with test_engine.connect() as conn:
        return await conn.run_sync(
            lambda sync_conn: sa.inspect(sync_conn).get_foreign_keys(table_name)
        )


async def _enum_values(test_engine, enum_name: str) -> list[str]:
    async with test_engine.connect() as conn:
        result = await conn.execute(
            sa.text(
                "SELECT enumlabel FROM pg_enum e "
                "JOIN pg_type t ON e.enumtypid = t.oid "
                "WHERE t.typname = :name ORDER BY e.enumsortorder"
            ),
            {"name": enum_name},
        )
        return [row[0] for row in result.all()]


# ---------------------------------------------------------------------------
# New CanonicalDocument columns
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("col_name,expected_nullable", list(_NEW_COLUMNS.items()))
@pytest.mark.asyncio
async def test_files_has_new_canonical_document_columns(
    test_engine, col_name, expected_nullable
):
    cols = await _columns(test_engine, "files")
    assert col_name in cols, (
        f"files.{col_name} must be added by CANON-DOC-1 — it is part of "
        "the CanonicalDocument shape that unifies file-source and "
        "record-source connectors. See product-feature-roadmap/"
        "enterprise-search/unified-doc-parse-chunk.md."
    )
    assert cols[col_name]["nullable"] is expected_nullable, (
        f"files.{col_name} expected nullable={expected_nullable}; "
        f"got nullable={cols[col_name]['nullable']}. The canon-doc design "
        "specifies which fields are required (every doc has one) and "
        "which are optional (per source_type)."
    )


@pytest.mark.asyncio
async def test_files_source_type_is_an_enum_with_canonical_values(test_engine):
    cols = await _columns(test_engine, "files")
    assert "source_type" in cols
    # SourceType is a closed vocabulary; new kinds require a migration.
    values = await _enum_values(test_engine, "file_source_type")
    assert tuple(sorted(values)) == tuple(sorted(_CANONICAL_SOURCE_TYPES)), (
        "file_source_type enum must contain exactly the 12 canonical "
        "kinds from unified-doc-parse-chunk.md (Source_type — closed "
        f"vocabulary). Got: {sorted(values)!r}; "
        f"expected: {sorted(_CANONICAL_SOURCE_TYPES)!r}."
    )


@pytest.mark.asyncio
async def test_files_parent_doc_id_is_self_fk_with_cascade(test_engine):
    fks = await _foreign_keys(test_engine, "files")
    matching = [
        fk for fk in fks
        if "parent_doc_id" in fk["constrained_columns"]
    ]
    assert matching, (
        "files.parent_doc_id must have a self-FK on files.id so deleting "
        "a parent issue / thread cascades its comments / replies / "
        "attachments. The canon-doc parent/child model relies on this."
    )
    fk = matching[0]
    assert fk["referred_table"] == "files", (
        f"files.parent_doc_id must self-reference files; got {fk['referred_table']}"
    )
    assert "id" in fk["referred_columns"]
    on_delete = (fk.get("options") or {}).get("ondelete", "").upper()
    assert on_delete == "CASCADE", (
        "files.parent_doc_id FK must be ON DELETE CASCADE — deleting "
        f"the parent record cascades its children. Got ondelete={on_delete!r}."
    )


@pytest.mark.asyncio
async def test_files_viewers_defaults_to_empty_object(test_engine):
    """Default-deny invariant: a freshly-inserted row with no resolved
    ViewerSet must default to "{}" (empty principals list) so the row is
    invisible to retrieval until the ACL resolver populates it. This is
    the safe default-deny posture from unified-doc-parse-chunk.md §
    Default-deny invariants."""
    cols = await _columns(test_engine, "files")
    viewers = cols["viewers"]
    default = viewers.get("default") or ""
    # Postgres renders the JSONB default as "'{}'::jsonb" or similar.
    assert "{}" in str(default), (
        f"files.viewers default must be '{{}}' (empty object) to enforce "
        f"default-deny on ACL-unresolved rows. Got default={default!r}."
    )


# ---------------------------------------------------------------------------
# File-only columns relaxed to nullable
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("col_name", _RELAXED_TO_NULLABLE)
@pytest.mark.asyncio
async def test_files_file_only_columns_are_nullable(test_engine, col_name):
    cols = await _columns(test_engine, "files")
    assert col_name in cols, (
        f"files.{col_name} must still exist — it is kept for file-source "
        "connectors and only relaxed for record-source compatibility."
    )
    assert cols[col_name]["nullable"] is True, (
        f"files.{col_name} must become nullable in CANON-DOC-1 — record-"
        "source connectors (Jira issues, Confluence pages, Slack "
        "messages) have no filename / mime type / bytes / size / "
        "hash. The fields stay set for file-source rows; nullable "
        "support is what unifies the table."
    )
