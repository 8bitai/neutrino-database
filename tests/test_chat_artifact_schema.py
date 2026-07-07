"""
NC-151 (Slice A, C1) — the ``chat_artifact`` table.

The unified agent produces *artifacts*: renderable, addressable outputs a turn
emits — a governed structured chart/table/kpi, or a model-authored generative
HTML page ("a full dashboard page and more"). Today a chart lives only inside
the assistant message's JSON envelope (inherited from the DA agent), so it has
no durable, server-addressable identity — nothing can be opened in its own
view, versioned, or (Slice B) shared via link. This table gives an artifact
that identity.

It is deliberately a UNIFIED-AGENT primitive, not a DA/ES concept: the row
carries no pillar-specific columns; ``kind`` + a JSONB ``content`` payload
model every render family. DA's ECharts becomes just one ``kind`` ('chart')
producer/renderer, not the center.

Locked design points:

  * ``tenant_id`` / ``workspace_id`` NOT NULL, both FK CASCADE — an artifact is
    always grounded in exactly one tenant + workspace; deleting a workspace
    removes its artifacts (mirrors ``chat`` / ``chat_attachment``).
  * ``chat_id`` NOT NULL, FK CASCADE — an artifact is always produced within a
    conversation and dies with it. (Unlike an upload, it can never precede the
    chat: the agent produces it mid-turn, so the chat row already exists.)
  * ``message_id`` nullable, FK **SET NULL** — the producing assistant message.
    NOT CASCADE: an artifact is a durable, addressable snapshot meant to outlive
    an edited/deleted message (a shared link in Slice B must not 404 because the
    origin turn was trimmed). Deleting the message unlinks, it does not destroy.
  * ``created_by`` nullable, FK user SET NULL — known at insert, but a user
    deletion must not cascade-destroy their artifacts (mirrors ``chat.created_by``).
  * ``kind`` (chart | table | kpi | html | doc) is the render-family
    discriminator; drives both the FE renderer registry and the safety posture
    (structured kinds house-render; html/doc render in a sandboxed iframe).
  * ``content`` JSONB NOT NULL — the whole payload inline (structured spec+data,
    or {"html": ...} for generative). Inline rather than a MinIO blob because an
    artifact is small structured content the FE renders, not opaque bytes to
    download (that is ``chat_attachment``/NC-149). Large-HTML-to-blob is tracked
    debt, not a v1 concern.
  * ``version`` NOT NULL default 1 — Claude-style iterate-in-place ("update this
    artifact") bumps it later; the column exists now so the UX lands without a
    migration (TD-ARTIFACT-VERSIONING-UX).
  * ``derived_from_artifact_id`` nullable self-FK SET NULL — lineage for
    revisualize/fork; a derived artifact survives its parent's deletion.
  * ``deleted_at`` nullable — soft delete, so a partial index on the chat/message
    lookups stays lean.

The test engine builds schema from ``tables.py`` via ``metadata.create_all``
(see conftest), so this fails until the enum + table land in ``tables.py``; the
matching alembic migration is required separately for dev/prod.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa


# ---------------------------------------------------------------------------
# Helpers — same shape as test_chat_attachment_schema.py
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


def _ondelete(fk: dict) -> str | None:
    return (fk.get("options") or {}).get("ondelete")


def _fk_for(fks: list[dict], column: str) -> dict | None:
    return next(
        (fk for fk in fks if fk["constrained_columns"] == [column]), None
    )


# ---------------------------------------------------------------------------
# Columns + types
# ---------------------------------------------------------------------------


class TestChatArtifactColumns:
    @pytest.mark.asyncio
    async def test_table_and_core_columns_exist(self, test_engine):
        cols = await _columns(test_engine, "chat_artifact")
        expected = {
            "id",
            "tenant_id",
            "workspace_id",
            "chat_id",
            "message_id",
            "created_by",
            "kind",
            "title",
            "content",
            "version",
            "derived_from_artifact_id",
            "created_at",
            "updated_at",
            "deleted_at",
        }
        missing = expected - set(cols.keys())
        assert not missing, (
            f"chat_artifact is missing columns {sorted(missing)}. "
            f"Present: {sorted(cols.keys())}"
        )

    @pytest.mark.asyncio
    async def test_kind_is_native_enum(self, test_engine):
        udts = await _udt_names(test_engine, "chat_artifact")
        assert udts.get("kind") == "chat_artifact_kind", (
            "chat_artifact.kind must be the native chat_artifact_kind enum "
            "(the render-family discriminator), not free text. Got udt: "
            f"{udts.get('kind')!r}"
        )

    @pytest.mark.asyncio
    async def test_kind_enum_has_all_render_families(self, test_engine):
        """react is the single interactive path (supersedes inline ```jsx)."""
        async with test_engine.connect() as conn:
            rows = await conn.execute(
                sa.text(
                    "SELECT enumlabel FROM pg_enum e JOIN pg_type t "
                    "ON e.enumtypid = t.oid WHERE t.typname = 'chat_artifact_kind'"
                )
            )
            labels = {r[0] for r in rows.fetchall()}
        assert labels == {"chart", "table", "kpi", "html", "react", "doc"}, (
            f"chat_artifact_kind must carry all render families. Got: {sorted(labels)}"
        )

    @pytest.mark.asyncio
    async def test_content_is_jsonb_not_null(self, test_engine):
        cols = await _columns(test_engine, "chat_artifact")
        udts = await _udt_names(test_engine, "chat_artifact")
        assert udts.get("content") == "jsonb", (
            "chat_artifact.content must be JSONB (the inline render payload). "
            f"Got udt: {udts.get('content')!r}"
        )
        assert cols["content"]["nullable"] is False, (
            "chat_artifact.content is the artifact — it is never NULL."
        )

    @pytest.mark.asyncio
    async def test_version_not_null_defaults_one(self, test_engine):
        cols = await _columns(test_engine, "chat_artifact")
        assert cols["version"]["nullable"] is False, (
            "chat_artifact.version must be NOT NULL — every artifact is at least v1."
        )
        default = (cols["version"].get("default") or "")
        assert "1" in default, (
            "chat_artifact.version must default to 1 so producers need not set it. "
            f"Got default: {default!r}"
        )

    @pytest.mark.asyncio
    async def test_deleted_at_nullable_for_soft_delete(self, test_engine):
        cols = await _columns(test_engine, "chat_artifact")
        assert cols["deleted_at"]["nullable"] is True, (
            "chat_artifact.deleted_at is a soft-delete tombstone — nullable."
        )


# ---------------------------------------------------------------------------
# Foreign keys — scoping + durable-snapshot ondelete posture
# ---------------------------------------------------------------------------


class TestChatArtifactForeignKeys:
    @pytest.mark.asyncio
    async def test_tenant_and_workspace_cascade(self, test_engine):
        fks = await _foreign_keys(test_engine, "chat_artifact")
        for col, ref in (("tenant_id", "tenant"), ("workspace_id", "workspace")):
            fk = _fk_for(fks, col)
            assert fk is not None, f"chat_artifact.{col} must be a FK"
            assert fk["referred_table"] == ref
            assert _ondelete(fk) == "CASCADE", (
                f"chat_artifact.{col} must CASCADE — an artifact is bounded by "
                f"its {ref}."
            )

    @pytest.mark.asyncio
    async def test_chat_id_not_null_cascade(self, test_engine):
        cols = await _columns(test_engine, "chat_artifact")
        fks = await _foreign_keys(test_engine, "chat_artifact")
        assert cols["chat_id"]["nullable"] is False, (
            "chat_artifact.chat_id is NOT NULL — an artifact is always produced "
            "inside an existing conversation (unlike an upload, it never precedes it)."
        )
        fk = _fk_for(fks, "chat_id")
        assert fk and fk["referred_table"] == "chat"
        assert _ondelete(fk) == "CASCADE"

    @pytest.mark.asyncio
    async def test_message_id_nullable_set_null(self, test_engine):
        """The durable-snapshot posture: an artifact must outlive an edited or
        deleted message, so message deletion UNLINKS (SET NULL), never cascades
        the artifact away."""
        cols = await _columns(test_engine, "chat_artifact")
        fks = await _foreign_keys(test_engine, "chat_artifact")
        assert cols["message_id"]["nullable"] is True
        fk = _fk_for(fks, "message_id")
        assert fk and fk["referred_table"] == "message"
        assert _ondelete(fk) == "SET NULL", (
            "chat_artifact.message_id must SET NULL on delete — a durable/"
            "shareable artifact cannot 404 because its origin turn was trimmed."
        )

    @pytest.mark.asyncio
    async def test_created_by_set_null(self, test_engine):
        fks = await _foreign_keys(test_engine, "chat_artifact")
        fk = _fk_for(fks, "created_by")
        assert fk and fk["referred_table"] == "user"
        assert _ondelete(fk) == "SET NULL", (
            "chat_artifact.created_by must SET NULL — a departed author must not "
            "cascade-destroy their artifacts (mirrors chat.created_by)."
        )

    @pytest.mark.asyncio
    async def test_derived_from_is_self_fk_set_null(self, test_engine):
        """Lineage for revisualize/fork; a derived artifact survives its parent."""
        fks = await _foreign_keys(test_engine, "chat_artifact")
        fk = _fk_for(fks, "derived_from_artifact_id")
        assert fk is not None, "derived_from_artifact_id must be a FK (lineage)"
        assert fk["referred_table"] == "chat_artifact", (
            "derived_from_artifact_id is a self-reference to chat_artifact."
        )
        assert _ondelete(fk) == "SET NULL"


# ---------------------------------------------------------------------------
# Indexes — chat list + message rehydration
# ---------------------------------------------------------------------------


class TestChatArtifactIndexes:
    @pytest.mark.asyncio
    async def test_chat_list_index_partial_on_deleted_at(self, test_engine):
        """Listing a chat's artifacts: WHERE chat_id = :c AND deleted_at IS NULL."""
        indexes = await _indexes(test_engine, "chat_artifact")
        has = any(
            ix["column_names"] and ix["column_names"][0] == "chat_id"
            for ix in indexes
        )
        assert has, (
            "chat_artifact needs a chat_id index for per-chat listing. "
            f"Indexes: {[ix['name'] for ix in indexes]}"
        )

    @pytest.mark.asyncio
    async def test_message_lookup_index(self, test_engine):
        """Rehydrating a message's artifacts on reload keys off message_id."""
        indexes = await _indexes(test_engine, "chat_artifact")
        has = any(
            ix["column_names"] and ix["column_names"][0] == "message_id"
            for ix in indexes
        )
        assert has, (
            "chat_artifact needs a message_id index for reload rehydration. "
            f"Indexes: {[ix['name'] for ix in indexes]}"
        )
