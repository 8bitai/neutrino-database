"""OpenFGA model migrator — the ``alembic upgrade head`` analogue (NC-113-a).

OpenFGA authorization models are immutable + versioned and are written only at
store creation, so a model change in source never reaches existing stores.
This migrator sweeps every store and writes the canonical model to any store
whose deployed model is missing or not the current schema — converging all
stores. Run it on deploy, right after ``alembic upgrade head``.

Properties:
  * **Idempotent** — a store already at head (semantic hash matches) is skipped;
    re-running writes nothing.
  * **Isolated** — a per-store failure is captured in the report, never aborts
    the sweep.
  * **Stateless** — drift is decided by comparing the deployed model's semantic
    hash to the source; no bookkeeping table. (A ``store_id -> model_hash``
    version table is the documented upgrade if model-version bloat matters.)

``migrate_all_stores`` is transport-agnostic — it talks to an ``FgaAdminClient``
protocol so it's unit-testable without a live OpenFGA. The concrete openfga_sdk
client + CLI live in ``_client.py`` / ``__main__.py``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

from neutrino_database.fga.model import (
    MODEL_VERSION,
    SOURCE_MODEL_HASH,
    load_model,
    model_hash,
)

logger = logging.getLogger(__name__)


class FgaAdminClient(Protocol):
    """The narrow OpenFGA admin surface the migrator needs."""

    async def list_store_ids(self) -> list[str]: ...

    async def read_latest_model(self, store_id: str) -> dict[str, Any] | None: ...

    async def write_model(self, store_id: str, model: dict[str, Any]) -> str: ...


@dataclass
class MigrationReport:
    """Outcome of a migrate sweep — every store lands in exactly one bucket."""

    migrated: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    model_version: str = MODEL_VERSION

    @property
    def total(self) -> int:
        return len(self.migrated) + len(self.skipped) + len(self.failed)

    @property
    def ok(self) -> bool:
        return not self.failed

    def as_dict(self) -> dict[str, Any]:
        return {
            "model_version": self.model_version,
            "total": self.total,
            "migrated": self.migrated,
            "skipped": self.skipped,
            "failed": self.failed,
            "ok": self.ok,
        }


async def migrate_all_stores(client: FgaAdminClient) -> MigrationReport:
    """Bring every store to the canonical model. See module docstring."""
    source = load_model()
    report = MigrationReport()

    store_ids = await client.list_store_ids()
    for store_id in store_ids:
        try:
            deployed = await client.read_latest_model(store_id)
            if deployed is not None and model_hash(deployed) == SOURCE_MODEL_HASH:
                report.skipped.append(store_id)
                continue
            await client.write_model(store_id, source)
            report.migrated.append(store_id)
            logger.info("[fga-migrate] store=%s -> wrote model %s", store_id, MODEL_VERSION)
        except Exception as exc:  # isolate: one bad store must not abort the sweep
            report.failed.append((store_id, str(exc)))
            logger.error("[fga-migrate] store=%s FAILED: %s", store_id, exc)

    logger.info(
        "[fga-migrate] done: total=%d migrated=%d skipped=%d failed=%d",
        report.total, len(report.migrated), len(report.skipped), len(report.failed),
    )
    return report


# ── CLI: python -m neutrino_database.fga.migrate ──────────────────────────
# The openfga_sdk import stays lazy (inside the CLI) so importing
# ``migrate_all_stores`` — for tests or in-process callers — never requires the
# SDK; only running the CLI does.


async def _cli() -> int:
    import json
    import os

    from neutrino_database.fga._client import OpenFgaAdminClient

    api_url = os.environ.get("OPENFGA_API_URL", "http://localhost:8080")
    report = await migrate_all_stores(OpenFgaAdminClient(api_url))
    print(json.dumps(report.as_dict(), indent=2))
    return 0 if report.ok else 1


def main() -> None:
    import asyncio
    import sys

    sys.exit(asyncio.run(_cli()))


if __name__ == "__main__":
    main()
