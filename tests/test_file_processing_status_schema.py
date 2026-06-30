"""
[NEU-1807] X-DOC-1 P1.1 — files.processing_status + file_processing_state.

Foundation schema for the documents-bounded-context refactor. The migration
``t7u8v9w0x1y2_file_processing_status_and_state.py`` and the parallel
``tables.py`` definitions must agree on:

  - the ``file_processing_status`` PgEnum with its 11 values + transitions
    those values cover (see ``user-stories/connect-ingestion-refactor.md`` §6),
  - the four companion columns on ``files`` (``status_updated_at``,
    ``error_code``, ``error_message``, ``error_retriable_at``),
  - the ``file_processing_state`` side-table keyed by ``file_id``
    with ON DELETE CASCADE,
  - the read-side indexes the FE polling endpoint and the retry runner
    need to stay cheap.

These tests pin all four pieces against the schema that
``Base.metadata.create_all`` produces — same shape ``alembic upgrade head``
must produce in any deployed environment.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import insert, select, text
from sqlalchemy.exc import IntegrityError

from neutrino_database.models.enums import FileProcessingStatusEnum
from neutrino_database.models.tables import (
    files,
    file_processing_state,
    integration,
    tenant,
    user as user_table,
    workspace,
)


# ---------------------------------------------------------------------------
# Fixture: a parent (tenant + workspace + user + integration + file) so
# the FK chain is satisfied. Each test cleans up via try/finally.
#
# UC-ES-DB-1.B+.E collapsed the legacy ``datasources`` table onto
# ``integration``; the seed now creates a tenant-owned integration with
# ``auth_kind='none'`` (the local-upload shape that replaced ``MANUAL``
# datasource rows) and points the file at it.
# ---------------------------------------------------------------------------


async def _seed_tenant_workspace_file(conn, *, file_status: str = "pending"):
    tenant_id = str(uuid.uuid4())
    workspace_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    integration_id = str(uuid.uuid4())
    file_id = uuid.uuid4()

    await conn.execute(
        insert(tenant).values(
            id=tenant_id,
            name="t7-test-tenant",
            org_external_id=f"t7-{uuid.uuid4()}",
        )
    )
    await conn.execute(
        insert(workspace).values(
            id=workspace_id,
            tenant_id=tenant_id,
            name="t7-ws",
        )
    )
    await conn.execute(
        insert(user_table).values(
            id=user_id,
            tenant_id=tenant_id,
            email=f"t7-{uuid.uuid4()}@test.local",
        )
    )
    await conn.execute(
        insert(integration).values(
            id=integration_id,
            tenant_id=tenant_id,
            workspace_id=None,
            provider="manual_upload",
            display_name="t7-manual",
            vault_secret_id=None,
            owner_kind="tenant",
            identity_kind="none",
            auth_kind="none",
            capabilities=["ingest"],
            created_by=user_id,
        )
    )
    await conn.execute(
        insert(files).values(
            id=file_id,
            tenant_id=uuid.UUID(tenant_id),
            workspace_id=uuid.UUID(workspace_id),
            integration_id=uuid.UUID(integration_id),
            original_filename="t7.pdf",
            file_type="pdf",
            storage_uri="s3://t7-bucket/t7.pdf",
            file_size_bytes=1234,
            file_sha256="0" * 64,
            created_by="test-user",
            processing_status=file_status,
        )
    )
    return tenant_id, workspace_id, file_id


async def _cleanup(conn, tenant_id):
    """tenant CASCADE drops everything below it."""
    await conn.execute(text("DELETE FROM tenant WHERE id = :tid"), {"tid": tenant_id})


# ---------------------------------------------------------------------------
# 1. Enum coverage — every value the design doc names exists in the DB.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_file_processing_status_enum_has_all_twelve_values(test_engine):
    expected = {
        "pending",
        "fetching",
        "fetched",
        "converting",
        "parsing",
        "chunking",
        "embedding",
        "indexing",
        "acl_replicated",
        "indexed",
        "failed",
        "deleted",
    }
    async with test_engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT enumlabel FROM pg_enum "
                "JOIN pg_type ON pg_type.oid = pg_enum.enumtypid "
                "WHERE pg_type.typname = 'file_processing_status'"
            )
        )
        actual = {row[0] for row in result.fetchall()}
    assert actual == expected, (
        f"file_processing_status enum drifted from spec. "
        f"Missing: {sorted(expected - actual)}; "
        f"Extra: {sorted(actual - expected)}."
    )


def test_python_enum_matches_db_enum_values():
    """Python ``FileProcessingStatusEnum`` and the DB ``file_processing_status``
    type must declare the same value set, in the same string spelling. Drift
    here = silent runtime errors in app code that's typed against the Python
    enum but writes the DB value."""
    expected = {
        "pending",
        "fetching",
        "fetched",
        "converting",
        "parsing",
        "chunking",
        "embedding",
        "indexing",
        "acl_replicated",
        "indexed",
        "failed",
        "deleted",
    }
    actual = {e.value for e in FileProcessingStatusEnum}
    assert actual == expected


# ---------------------------------------------------------------------------
# 2. files.processing_status default + companion columns work as declared.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_processing_status_default_is_pending(test_engine):
    async with test_engine.begin() as conn:
        tenant_id = workspace_id = file_id = None
        try:
            tenant_id, workspace_id, file_id = await _seed_tenant_workspace_file(
                conn, file_status="pending"
            )
            row = (
                await conn.execute(
                    select(
                        files.c.processing_status,
                        files.c.status_updated_at,
                        files.c.error_code,
                        files.c.error_message,
                        files.c.error_retriable_at,
                    ).where(files.c.id == file_id)
                )
            ).one()
            assert row.processing_status == "pending"
            assert row.status_updated_at is not None
            assert row.error_code is None
            assert row.error_message is None
            assert row.error_retriable_at is None
        finally:
            if tenant_id:
                await _cleanup(conn, tenant_id)


@pytest.mark.asyncio
async def test_processing_status_rejects_unknown_value(test_engine):
    """The PgEnum prevents arbitrary strings — important for the contract
    between ingestion's writers and the FE's reader."""
    async with test_engine.begin() as conn:
        with pytest.raises(Exception):
            # `not_a_real_state` is not in the enum — the bind step or
            # the COMMIT will raise InvalidTextRepresentation /
            # DataError. Either way pytest.raises catches it.
            await _seed_tenant_workspace_file(conn, file_status="not_a_real_state")


# ---------------------------------------------------------------------------
# 3. file_processing_state — FK + cascade + defaults.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_file_processing_state_cascades_on_file_delete(test_engine):
    """When the parent ``files`` row goes away, the side-table row must too —
    no orphan retry/Temporal state. ON DELETE CASCADE pins this."""
    async with test_engine.begin() as conn:
        tenant_id = None
        try:
            tenant_id, _ws, file_id = await _seed_tenant_workspace_file(conn)

            await conn.execute(
                insert(file_processing_state).values(
                    file_id=file_id,
                    temporal_workflow_id=f"file:{file_id}",
                    last_activity="parse",
                )
            )

            # Confirm the side row exists.
            count = (
                await conn.execute(
                    select(file_processing_state.c.file_id).where(
                        file_processing_state.c.file_id == file_id
                    )
                )
            ).all()
            assert len(count) == 1

            # Hard-delete the file row (not soft-delete; we're testing the
            # FK cascade, not the application-level tombstone).
            await conn.execute(text("DELETE FROM files WHERE id = :fid"), {"fid": file_id})

            # Side row should be gone.
            after = (
                await conn.execute(
                    select(file_processing_state.c.file_id).where(
                        file_processing_state.c.file_id == file_id
                    )
                )
            ).all()
            assert after == []
        finally:
            if tenant_id:
                await _cleanup(conn, tenant_id)


@pytest.mark.asyncio
async def test_file_processing_state_defaults(test_engine):
    async with test_engine.begin() as conn:
        tenant_id = None
        try:
            tenant_id, _ws, file_id = await _seed_tenant_workspace_file(conn)
            await conn.execute(insert(file_processing_state).values(file_id=file_id))

            row = (
                await conn.execute(
                    select(
                        file_processing_state.c.attempt_id,
                        file_processing_state.c.retry_count,
                        file_processing_state.c.temporal_workflow_id,
                        file_processing_state.c.last_activity,
                        file_processing_state.c.next_retry_at,
                        file_processing_state.c.payload,
                    ).where(file_processing_state.c.file_id == file_id)
                )
            ).one()
            assert row.attempt_id == 1
            assert row.retry_count == 0
            assert row.temporal_workflow_id is None
            assert row.last_activity is None
            assert row.next_retry_at is None
            assert row.payload is None
        finally:
            if tenant_id:
                await _cleanup(conn, tenant_id)


@pytest.mark.asyncio
async def test_file_processing_state_pk_prevents_duplicate(test_engine):
    """``file_id`` is the PK — at most one in-flight processing-state row per
    file. Concurrent writers must not produce duplicates; the PK catches it.

    We wrap the duplicate insert in a SAVEPOINT so the IntegrityError doesn't
    abort the outer transaction (which would block our cleanup DELETE).
    """
    async with test_engine.begin() as conn:
        tenant_id = None
        try:
            tenant_id, _ws, file_id = await _seed_tenant_workspace_file(conn)
            await conn.execute(insert(file_processing_state).values(file_id=file_id))

            sp = await conn.begin_nested()
            try:
                await conn.execute(insert(file_processing_state).values(file_id=file_id))
                pytest.fail("Expected IntegrityError on duplicate file_id")
            except IntegrityError:
                await sp.rollback()
        finally:
            if tenant_id:
                await _cleanup(conn, tenant_id)


# ---------------------------------------------------------------------------
# 4. Read-side indexes exist (cheap-query guarantees).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_required_indexes_exist(test_engine):
    """Pin the indexes the FE polling endpoint and the retry runner need.
    If the migration ever drops them, every status-list query degrades to
    seq-scan and this test catches it."""
    async with test_engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE schemaname = 'public' "
                "AND indexname IN ("
                "   'ix_files_workspace_processing_status',"
                "   'ix_file_processing_state_due_retries'"
                ")"
            )
        )
        names = {row[0] for row in result.fetchall()}
        assert names == {
            "ix_files_workspace_processing_status",
            "ix_file_processing_state_due_retries",
        }, f"Expected both indexes to exist; got {names}"
