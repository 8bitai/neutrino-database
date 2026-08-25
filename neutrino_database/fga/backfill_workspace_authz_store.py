"""Backfill workspace_authz_store from existing OpenFGA stores.

Run this once per environment BEFORE any process hits the new
DocAclService client. After A4, ``_get_or_create_store`` never looks up
stores by name. A workspace whose ``{workspace_id}_file_permissions``
store already exists but has no mapping row will get a second empty
store on first access, and existing document-ACL tuples become
invisible.

This script lists OpenFGA stores, matches names
``{workspace_id}_file_permissions`` (the same shape as
``DocAclService._get_store_name``), and inserts
``workspace_authz_store (workspace_id, store_id, model_id)`` when the
row is missing. Idempotent: existing rows are skipped
(``ON CONFLICT DO NOTHING``), including crashed-winner NULL claims.

Do not run against production from a workstation without an explicit
ops plan. A NULL ``store_id`` claim is not filled here; unstick with
``DELETE FROM workspace_authz_store WHERE store_id IS NULL``.

Usage::

    OPENFGA_API_URL=http://localhost:8080 \\
    DATABASE_URL=postgresql://... \\
        python -m neutrino_database.fga.backfill_workspace_authz_store

    python -m neutrino_database.fga.backfill_workspace_authz_store --dry-run
"""

from __future__ import annotations

import logging
import uuid

from neutrino_database.fga.migrate import MANAGED_STORE_SUFFIX

logger = logging.getLogger(__name__)


def workspace_id_from_store_name(name: str) -> str | None:
    """Inverse of ``DocAclService._get_store_name``.

    Returns the workspace id when ``name`` is
    ``{workspace_id}_file_permissions`` and the prefix is a UUID;
    otherwise None (tenant RBAC stores, empty prefix, junk names).
    """
    if not name.endswith(MANAGED_STORE_SUFFIX):
        return None
    prefix = name[: -len(MANAGED_STORE_SUFFIX)]
    if not prefix:
        return None
    try:
        uuid.UUID(prefix)
    except ValueError:
        return None
    return prefix


def _model_id(model: dict | None) -> str | None:
    if not model:
        return None
    value = model.get("id") or model.get("authorization_model_id")
    return value or None


async def collect_mappings(client) -> list[tuple[str, str, str]]:
    """Return ``(workspace_id, store_id, model_id)`` for managed stores.

    First store wins when OpenFGA has duplicate names. Stores with no
    authorization model are skipped.
    """
    mappings: list[tuple[str, str, str]] = []
    seen: dict[str, str] = {}
    stores = await client.list_stores()
    for store_id, name in stores:
        workspace_id = workspace_id_from_store_name(name)
        if workspace_id is None:
            continue
        if workspace_id in seen:
            logger.warning(
                "duplicate store name for workspace %s: keeping %s, skipping %s",
                workspace_id,
                seen[workspace_id],
                store_id,
            )
            continue
        model_id = _model_id(await client.read_latest_model(store_id))
        if not model_id:
            logger.warning(
                "store %s (%s) has no authorization model; skipping",
                store_id,
                name,
            )
            continue
        seen[workspace_id] = store_id
        mappings.append((workspace_id, store_id, model_id))
    return mappings


def upsert_mappings(conn, mappings: list[tuple[str, str, str]], *, dry_run: bool) -> dict[str, int]:
    """Insert missing ``workspace_authz_store`` rows. Never overwrites."""
    from sqlalchemy import select
    from sqlalchemy.dialects.postgresql import insert
    from sqlalchemy.exc import IntegrityError

    from neutrino_database.models.tables import workspace, workspace_authz_store

    counts = {
        "inserted": 0,
        "skipped_existing": 0,
        "skipped_no_workspace": 0,
        "skipped_conflict": 0,
        "would_insert": 0,
    }
    for workspace_id, store_id, model_id in mappings:
        ws_row = conn.execute(
            select(workspace.c.id).where(workspace.c.id == workspace_id)
        ).first()
        if ws_row is None:
            logger.warning(
                "no workspace row for %s (store %s); skipping",
                workspace_id,
                store_id,
            )
            counts["skipped_no_workspace"] += 1
            continue

        existing = conn.execute(
            select(workspace_authz_store).where(
                workspace_authz_store.c.workspace_id == workspace_id
            )
        ).first()
        if existing is not None:
            if existing.store_id is None:
                logger.warning(
                    "workspace %s has a NULL store_id claim row; not filling",
                    workspace_id,
                )
            elif existing.store_id != store_id:
                logger.warning(
                    "workspace %s already mapped to store %s; not replacing with %s",
                    workspace_id,
                    existing.store_id,
                    store_id,
                )
            counts["skipped_existing"] += 1
            continue

        if dry_run:
            logger.info(
                "dry-run: would insert workspace_id=%s store_id=%s model_id=%s",
                workspace_id,
                store_id,
                model_id,
            )
            counts["would_insert"] += 1
            continue

        try:
            with conn.begin_nested():
                result = conn.execute(
                    insert(workspace_authz_store)
                    .values(
                        workspace_id=workspace_id,
                        store_id=store_id,
                        model_id=model_id,
                    )
                    .on_conflict_do_nothing(index_elements=["workspace_id"])
                )
                if result.rowcount == 1:
                    counts["inserted"] += 1
                else:
                    counts["skipped_existing"] += 1
        except IntegrityError:
            logger.warning(
                "insert failed for workspace %s store %s (FK or constraint)",
                workspace_id,
                store_id,
            )
            counts["skipped_conflict"] += 1
    return counts


async def run(*, dry_run: bool = False) -> dict[str, int]:
    import os

    from sqlalchemy import create_engine

    from neutrino_database.config import settings
    from neutrino_database.fga._client import OpenFgaAdminClient

    api_url = os.environ.get("OPENFGA_API_URL", "http://localhost:8080")
    api_token = os.environ.get("OPENFGA_API_TOKEN") or None
    allow_insecure_http = os.environ.get("OPENFGA_ALLOW_INSECURE_HTTP", "").lower() in (
        "1",
        "true",
        "yes",
    )
    client = OpenFgaAdminClient(
        api_url,
        api_token=api_token,
        allow_insecure_http=allow_insecure_http,
    )
    mappings = await collect_mappings(client)

    sync_url = settings.DATABASE_URL.replace(
        "postgresql+asyncpg://",
        "postgresql+psycopg2://",
    )
    engine = create_engine(sync_url)
    try:
        with engine.begin() as conn:
            counts = upsert_mappings(conn, mappings, dry_run=dry_run)
    finally:
        engine.dispose()

    counts["mapped"] = len(mappings)
    return counts


def main() -> None:
    import argparse
    import asyncio
    import json
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    parser = argparse.ArgumentParser(
        description=(
            "One-shot backfill of workspace_authz_store from existing "
            "{workspace_id}_file_permissions OpenFGA stores. Run once per "
            "environment BEFORE any process hits the new client."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List mappings that would be inserted; write nothing",
    )
    args = parser.parse_args()
    counts = asyncio.run(run(dry_run=args.dry_run))
    print(json.dumps(counts, indent=2))
    sys.exit(0)


if __name__ == "__main__":
    main()
