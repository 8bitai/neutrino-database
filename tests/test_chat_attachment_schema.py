"""
NC-137 (Slice A1) — the ``chat_attachment`` table.

Unified Chat needs a Claude-style file-upload lane: a user attaches a
CSV/Excel, PDF, or image to a conversation and the agent analyses it in
the same turn. These attachments are a DIFFERENT lifecycle from
Enterprise Search ingestion (permanent, indexed, ACL'd) and from the DA
Excel-dataset path (Excel -> Postgres queryable schema): they are
**ephemeral, conversation-scoped, TTL'd, and never indexed**. That
distinct lifecycle is exactly why this is its own table rather than a
JSONB blob hung off ``message`` — it has its own status state machine
(``uploaded -> processing -> ready``/``failed``), its own TTL/GC sweep,
and its own delete-with-chat cascade.

Locked design points:

  * ``tenant_id`` / ``workspace_id`` NOT NULL, both FK CASCADE — an
    attachment is always grounded in exactly one tenant + workspace, and
    deleting a workspace removes its attachments (mirrors ``chat`` and
    ``da_enrichment_run``).
  * ``chat_id`` nullable, FK CASCADE. Nullable because the upload can
    precede the chat row (the FE composer uploads on paperclip-click,
    before the first message creates the chat); set when the message is
    sent. CASCADE so deleting a chat purges its attachments; NULL
    (never-linked) orphans are reaped by the TTL sweep.
  * ``message_id`` nullable, FK CASCADE — linked when the message is
    sent; the attachment's lifecycle is a subset of its message's.
  * ``uploaded_by`` nullable, FK user SET NULL — we always know the
    uploader at insert, but a user deletion must not orphan-cascade the
    row away (mirrors ``chat.created_by``).
  * ``kind`` (tabular | document | image) drives lane dispatch and the
    FE chip icon; ``status`` (uploaded | processing | ready | failed)
    is the state machine. Tabular/image land ``ready`` immediately;
    document goes ``processing`` while MinerU extracts (Slice B).
  * ``storage_key`` is the MinIO object key for the raw bytes.
    ``extracted_text_key`` holds the MinerU markdown key for the
    document lane (NULL otherwise).
  * ``expires_at`` powers the TTL/GC sweep; a partial index on it keyed
    ``WHERE deleted_at IS NULL`` serves the reaper without bloating on
    soft-deleted rows.

The test engine builds schema from ``tables.py`` via
``metadata.create_all`` (see conftest), so this fails until the enums +
table land in ``tables.py``; the matching alembic migration is required
separately for dev/prod.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa


# ---------------------------------------------------------------------------
# Helpers — same shape as test_chat_workspace_scoping_schema.py
# ---------------------------------------------------------------------------


async def _columns(test_engine, table_name: str) -> dict:
    async with test_engine.connect() as conn:
        return await conn.run_sync(
            lambda sync_conn: {
                c["name"]: c
                for c in sa.inspect(sync_conn).get_columns(table_name)
            }
        )


async def _indexes(test_engine, table_name: str) -> list[dict]:
    async with test_engine.connect() as conn:
        return await conn.run_sync(
            lambda sync_conn: sa.inspect(sync_conn).get_indexes(table_name)
        )


async def _foreign_keys(test_engine, table_name: str) -> list[dict]:
    async with test_engine.connect() as conn:
        return await conn.run_sync(
            lambda sync_conn: sa.inspect(sync_conn).get_foreign_keys(table_name)
        )


async def _partial_index_predicates(test_engine, table_name: str) -> dict[str, str]:
    async with test_engine.connect() as conn:
        result = await conn.execute(
            sa.text(
                """
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE tablename = :table_name
                """
            ),
            {"table_name": table_name},
        )
        out: dict[str, str] = {}
        for name, indexdef in result.fetchall():
            upper = indexdef.upper()
            where_pos = upper.rfind(" WHERE ")
            if where_pos >= 0:
                out[name] = indexdef[where_pos + len(" WHERE ") :].strip()
        return out


def _ondelete(fk: dict) -> str | None:
    return (fk.get("options") or {}).get("ondelete")


async def _udt_names(test_engine, table_name: str) -> dict[str, str]:
    """{column: udt_name} from information_schema — the ground-truth backing
    type. Native PG enums surface as data_type 'USER-DEFINED' with udt_name set
    to the enum type; async reflection's str(type) misleadingly renders VARCHAR,
    so we read the catalog directly."""
    async with test_engine.connect() as conn:
        result = await conn.execute(
            sa.text(
                """
                SELECT column_name, udt_name
                FROM information_schema.columns
                WHERE table_name = :t
                """
            ),
            {"t": table_name},
        )
        return {name: udt for name, udt in result.fetchall()}


def _fk_for(fks: list[dict], column: str) -> dict | None:
    return next(
        (fk for fk in fks if fk["constrained_columns"] == [column]), None
    )


# ---------------------------------------------------------------------------
# Columns
# ---------------------------------------------------------------------------


class TestChatAttachmentColumns:
    @pytest.mark.asyncio
    async def test_table_exists_with_core_columns(self, test_engine):
        cols = await _columns(test_engine, "chat_attachment")
        for required in (
            "id",
            "tenant_id",
            "workspace_id",
            "chat_id",
            "message_id",
            "uploaded_by",
            "filename",
            "mime_type",
            "size_bytes",
            "storage_key",
            "kind",
            "status",
            "extracted_text_key",
            "error",
            "expires_at",
            "created_at",
            "updated_at",
            "deleted_at",
        ):
            assert required in cols, (
                f"chat_attachment.{required} is part of the locked attachment "
                f"shape. Existing columns: {sorted(cols.keys())}"
            )

    @pytest.mark.asyncio
    async def test_scoping_columns_not_null(self, test_engine):
        cols = await _columns(test_engine, "chat_attachment")
        for nn in ("tenant_id", "workspace_id", "filename", "mime_type", "size_bytes", "storage_key"):
            assert cols[nn]["nullable"] is False, (
                f"chat_attachment.{nn} must be NOT NULL — an attachment with no "
                f"{nn} cannot be authorized, fetched, or staged."
            )

    @pytest.mark.asyncio
    async def test_link_columns_nullable(self, test_engine):
        """chat_id / message_id are set at send time, so nullable at insert."""
        cols = await _columns(test_engine, "chat_attachment")
        assert cols["chat_id"]["nullable"] is True
        assert cols["message_id"]["nullable"] is True
        assert cols["expires_at"]["nullable"] is True


# ---------------------------------------------------------------------------
# Foreign keys
# ---------------------------------------------------------------------------


class TestChatAttachmentForeignKeys:
    @pytest.mark.asyncio
    async def test_tenant_and_workspace_cascade(self, test_engine):
        fks = await _foreign_keys(test_engine, "chat_attachment")
        for col, table in (("tenant_id", "tenant"), ("workspace_id", "workspace")):
            fk = _fk_for(fks, col)
            assert fk is not None, f"chat_attachment.{col} must FK to {table}"
            assert fk["referred_table"] == table
            assert _ondelete(fk) == "CASCADE", (
                f"chat_attachment.{col} FK must CASCADE — deleting a {table} "
                "purges its ephemeral attachments."
            )

    @pytest.mark.asyncio
    async def test_chat_and_message_cascade(self, test_engine):
        fks = await _foreign_keys(test_engine, "chat_attachment")
        for col, table in (("chat_id", "chat"), ("message_id", "message")):
            fk = _fk_for(fks, col)
            assert fk is not None, f"chat_attachment.{col} must FK to {table}"
            assert fk["referred_table"] == table
            assert _ondelete(fk) == "CASCADE", (
                f"chat_attachment.{col} FK must CASCADE — an attachment's "
                f"lifecycle is a subset of its {table}'s."
            )

    @pytest.mark.asyncio
    async def test_uploaded_by_set_null(self, test_engine):
        fks = await _foreign_keys(test_engine, "chat_attachment")
        fk = _fk_for(fks, "uploaded_by")
        assert fk is not None and fk["referred_table"] == "user"
        assert _ondelete(fk) == "SET NULL", (
            "chat_attachment.uploaded_by must SET NULL on user delete — a "
            "departed uploader must not cascade-delete in-flight attachments "
            "(mirrors chat.created_by)."
        )


# ---------------------------------------------------------------------------
# Enums + status default
# ---------------------------------------------------------------------------


class TestChatAttachmentEnums:
    @pytest.mark.asyncio
    async def test_status_defaults_to_uploaded(self, test_engine):
        cols = await _columns(test_engine, "chat_attachment")
        default = (cols["status"].get("default") or "")
        assert "uploaded" in default, (
            "chat_attachment.status must default to 'uploaded' — the row is "
            f"created the moment bytes land. Got default: {default!r}"
        )

    @pytest.mark.asyncio
    async def test_kind_and_status_are_native_enums(self, test_engine):
        udts = await _udt_names(test_engine, "chat_attachment")
        assert udts.get("kind") == "chat_attachment_kind", (
            "chat_attachment.kind must be the native chat_attachment_kind enum, "
            f"not a free-text column. Got udt: {udts.get('kind')!r}"
        )
        assert udts.get("status") == "chat_attachment_status", (
            "chat_attachment.status must be the native chat_attachment_status "
            f"enum. Got udt: {udts.get('status')!r}"
        )


# ---------------------------------------------------------------------------
# Indexes — chat list + TTL sweep
# ---------------------------------------------------------------------------


class TestChatAttachmentIndexes:
    @pytest.mark.asyncio
    async def test_chat_list_index_partial_on_deleted_at(self, test_engine):
        """Listing a chat's attachments: WHERE chat_id = :c AND deleted_at IS NULL."""
        indexes = await _indexes(test_engine, "chat_attachment")
        has_chat_index = any(
            ix["column_names"] and ix["column_names"][0] == "chat_id"
            for ix in indexes
        )
        assert has_chat_index, (
            "Expected an index leading on chat_id to serve the per-chat "
            f"attachment list. Existing: {[ix['name'] for ix in indexes]}"
        )
        predicates = await _partial_index_predicates(test_engine, "chat_attachment")
        assert any(
            "chat" in name.lower() and "deleted_at" in pred.lower()
            for name, pred in predicates.items()
        ), (
            "The per-chat attachment index must be partial on "
            f"deleted_at IS NULL. Indexes with WHERE: {predicates}"
        )

    @pytest.mark.asyncio
    async def test_expires_at_index_for_gc_sweep(self, test_engine):
        """The TTL/GC reaper scans expires_at; it needs an index."""
        indexes = await _indexes(test_engine, "chat_attachment")
        assert any(
            ix["column_names"] and ix["column_names"][0] == "expires_at"
            for ix in indexes
        ), (
            "Expected an index leading on expires_at for the TTL/GC sweep. "
            f"Existing: {[ix['name'] for ix in indexes]}"
        )
