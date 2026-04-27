# neutrino-database — Audit Log

> Per-ticket log of code/infra issues found while working in this repo, plus the fix applied. Append-only. Three-line format per issue: **Issue → Why → Fix**.
>
> Companion to the workspace-level `our-issues-list.md` (cross-repo backlog) and `our-engineering-standards.md` (the bar every fix must meet).

---

## NEU-1801 — DB Task 0a: pytest + Postgres test fixture (inaugural test infra)

**Branch:** `NEU-1801`
**Status:** Done (this commit).
**Scope:** Stand up the minimum test infrastructure required to TDD schema changes in this repo. No production behaviour changes — pure dev infra.

### Issues found and fixed in-flight

1. **No tests in the repo at all**
   *Why:* Schema changes (column additions, enum redefinitions, table renames) had nothing automated catching them. Migrations would silently drift from `tables.py` / `orm.py` and the consequences only surfaced once the gateway test suite (which depends on this repo) tried to round-trip the new shape.
   *Fix:* Added `tests/__init__.py` + `tests/conftest.py` with a session-scoped async Postgres engine bound to `TEST_DATABASE_URL`. Mirrors the gateway conftest's safety guard (refuses to run if `TEST_DATABASE_URL` is missing or equals `DATABASE_URL`) and brings the schema up via `Base.metadata.create_all`.

2. **Test deps not installable; no `requirements-dev.txt`**
   *Why:* `pytest`, `pytest-asyncio`, `asyncpg` not in any requirements file; conda env had no test tools.
   *Fix:* Added `requirements-dev.txt` pinned to the same versions as `neutrino-gateway/requirements-dev.txt` (pytest 8.4.2, pytest-asyncio 1.2.0, asyncpg 0.30.0, greenlet 3.2.4). Greenlet pinned explicitly — same SQLAlchemy-async-on-arm64 gotcha hit in the gateway.

3. **No pytest config**
   *Why:* Without `asyncio_mode=auto` and `testpaths`, pytest collection is uneven and async tests need explicit decorators per function.
   *Fix:* Added `pyproject.toml` with `[tool.pytest.ini_options]`. Coexists with the existing `pyproject.py` (which is a regular Python module exposing `PROJECT_ROOT`, not a packaging spec).

4. **No Makefile**
   *Why:* Every other repo in the workspace has a `make install` / `make test` / `make setup-test-db` shape. neutrino-database was the outlier.
   *Fix:* Slim `Makefile` mirroring gateway targets: `install`, `install-deps`, `test`, `test-verbose`, `setup-test-db`, `drop-test-db`, `recreate-test-db`, `clean`. Conda env is `neutrino-db` per the user's local convention. Full lint/format parity with gateway tracked as task #29 — kept out of this commit so the inaugural test-infra change stays focused.

5. **No `env.example`**
   *Why:* `.env` is gitignored (correctly) but newcomers had no template documenting the expected variables (`DATABASE_URL`, `TEST_DATABASE_URL`).
   *Fix:* Added `env.example` with both vars and the convention that `TEST_DATABASE_URL` must point at a separate DB (`neutrino_database_test_db`) from `DATABASE_URL` (the dev DB, conventionally `neutrino_v2`).

---

## NEU-1801 — Slice 1A wizard prereq: onboarding signal + multi-select pillars

**Branch:** `NEU-1801`
**Status:** Done (this commit).
**Scope:** Schema foundation for the Persona B onboarding wizard. Two coordinated changes that ship together so the FE/BE work that depends on them can land against real signals rather than proxies.

### Issues found and fixes applied

6. **No first-class "tenant has finished onboarding" signal**
   *Why:* The FE post-auth callback (Pattern B, see `neutrino-gateway/AUDIT.md` #38–41) needs to know whether to route a fresh-cookie user to `/welcome` or `/chat`. Today it uses the proxy `is_tenant_owner && !workspace_id`, which conflates "session has no workspace context yet" with "tenant has not been onboarded." The two states coincide today only because the gateway doesn't stamp `workspace_id` onto a brand-new owner's token; that breaks the moment the wizard saves the user's default workspace. Production-grade requires a real fact, not a proxy. Logged in `our-issues-list.md` and as task #24 / #11 (FE AUDIT.md).
   *Fix:* Added `tenant.onboarding_completed_at` (TIMESTAMP WITH TIME ZONE, NULL). Default NULL = onboarding not done. The upcoming `POST /api/v1/onboarding/complete` endpoint stamps it atomically (`UPDATE … WHERE onboarding_completed_at IS NULL` so concurrent calls don't double-stamp). Mirrored on the ORM (`Tenant.onboarding_completed_at`) and exercised by the round-trip schema test.

7. **`router_mode` enum conflates routing strategy with pillar enablement**
   *Why:* `orchestrator_config.router_mode` (`AUTO | SEARCH_ONLY | DA_ONLY | ACTION_ONLY`) is the only signal of "what does this workspace do." It cannot represent multi-select states like "Enterprise Search + Data Analytics but not Workflow," which the locked product model in `user-stories/tenant-onboarding.md` requires. The user explicitly wanted multi-select per workspace; the current schema forces a single-of-four choice.
   *Fix:* Added `pillar` ENUM with three values (`ENTERPRISE_SEARCH`, `DATA_ANALYTICS`, `WORKFLOW_EXECUTION`) — exactly the three product pillars. Added `workspace.enabled_pillars: pillar[] NOT NULL DEFAULT '{}'`. Backfilled from existing `orchestrator_config.router_mode` (AUTO → all three; SEARCH_ONLY → [ES]; etc.). The new column is the source-of-truth; `router_mode` stays for now so agent-platform reads continue to work, with the gateway writing both during the transition. Removal of `router_mode` is tracked as separate cleanup debt — not part of this slice. Mirrored on the ORM (`Workspace.enabled_pillars`) and exercised by default-empty + round-trip-with-all-three tests.

8. **`PillarEnum` placement and naming**
   *Why:* New enum needed a home that matched repo conventions. `enums.py` already collects every other domain enum.
   *Fix:* Added `PillarEnum(str, Enum)` next to `RouterModeEnum` in `neutrino_database/models/enums.py`. UPPERCASE values per `our-engineering-standards.md` §2 (the `ConnectionStatus` lowercase outlier doesn't get a sibling). Test asserts both the membership (exactly three values) and the casing rule.

9. **Migration design — reversible, transactional, backfill-correct**
   *Why:* `our-engineering-standards.md` §10 requires reversible migrations. The pillar enum must be created before the column that uses it; the column default must be safe to apply to existing rows (so no transient NULL-violation); the backfill must not silently miss workspaces that lack an `orchestrator_config` row.
   *Fix:* `alembic/versions/l9m0n1p2q3r4_add_onboarding_completed_at_and_enabled_pillars.py`. Up: adds `tenant.onboarding_completed_at`; creates the `pillar` enum (`checkfirst=True`); adds `workspace.enabled_pillars` with `server_default '{}'::pillar[]` so existing rows get the empty array safely; backfills via `UPDATE … FROM orchestrator_config` join — workspaces without an orchestrator_config row keep the empty default (correct: their pillars are unset). Down: drops both columns and the enum (lossless — `router_mode` carries the truth). Verified end-to-end against `neutrino_v2`: upgrade → assertion script → downgrade → assertion script → upgrade again.

10. **Test placement — schema tests in this repo, not the consumer's**
    *Why:* First instinct (called out by user) was to put the schema tests in `neutrino-gateway/tests/` because that's where the Postgres test infra already lives. That's overfitting to existing infra: the database repo owns its schema, so it owns its schema tests. Putting them elsewhere creates a permanent dependency where database repo changes can only be caught by a downstream test run.
    *Fix:* Built proper test infra here (issues 1–5) and put `tests/test_onboarding_pillar_schema.py` in this repo. 8 tests across 3 classes — column existence, type/nullability, default empty array, round-trip with all three pillars, enum membership, enum casing.
