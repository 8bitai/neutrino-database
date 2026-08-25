"""Document ACL client, shared by connector-service and ES-Ingestion.

Merged from the two ``openfga_service.py`` copies. Store names stay
``{workspace_id}_file_permissions`` so existing stores are not orphaned.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterable

from openfga_sdk.client import ClientConfiguration, OpenFgaClient
from openfga_sdk.credentials import CredentialConfiguration, Credentials
from openfga_sdk.client.models import (
    ClientCheckRequest,
    ClientListObjectsRequest,
    ClientWriteRequest,
)
from openfga_sdk.client.models.tuple import ClientTuple
from openfga_sdk.models import CreateStoreRequest, ReadRequestTupleKey

from neutrino_database.fga import load_model, model_hash, SOURCE_MODEL_HASH

# Stores whose model this process has already confirmed at-head (NC-113-a).
# The model is fixed per-process, so once verified we skip the read+hash on
# later accesses. Reset on restart so a new deploy re-checks.
_HEALED_STORES: set[str] = set()

# The relations that can carry tuples on a ``doc`` object. Both must be
# swept on delete: ``can_access`` holds legacy direct grants plus the
# ``user:*`` publish wildcard; ``viewer`` holds the canonical 4-kind
# grants (user / group#member / workspace#member / tenant#member).
_DOC_RELATIONS: tuple[str, ...] = ("can_access", "viewer")

# OpenFGA's transactional Write API caps writes+deletes per call; batches
# above this size must be chunked.
_WRITE_BATCH_SIZE = 100


def _chunks(iterable: Iterable, size: int) -> Iterable[list]:
    """Split an iterable into chunks of specified size."""
    buf: list = []
    for item in iterable:
        buf.append(item)
        if len(buf) >= size:
            yield buf
            buf = []
    if buf:
        yield buf


def _build_viewer_tuples_for_doc(
    *, doc_id: str, principals: list
) -> list[ClientTuple]:
    """CANON-DOC-4b helper — turn ResolvedPrincipal list into FGA tuples.

    The canonical 4-kind viewer contract maps to FGA's user-string
    syntax as:

      * USER             → ``user:{neutrino_id}``
      * GROUP            → ``group:{external_id}#member``    (lazy expansion)
      * WORKSPACE_PUBLIC → ``workspace:{workspace_id}#member``
      * TENANT_PUBLIC    → ``tenant:{tenant_id}#member``

    All tuples land on ``(doc:DOC_ID, viewer, …)`` — the new relation
    introduced in openfga_model.json alongside the legacy
    ``can_access``. Pure mechanics — no I/O — so it's unit-testable
    without an FGA instance.

    ``principals`` is typed as ``list`` to avoid a circular import on
    ResolvedPrincipal; the duck-typing relies on ``.kind`` and
    ``.neutrino_id`` attributes.
    """
    # Imported here to dodge a circular when openfga_service is loaded
    # before the canonical module (the resolver module imports from
    # neutrino_database which is fine, but we keep this side
    # decoupled).
    from neutrino_database.models.canonical import PrincipalKind

    out: list[ClientTuple] = []
    for p in principals:
        if p.kind == PrincipalKind.USER:
            user = f"user:{p.neutrino_id}"
        elif p.kind == PrincipalKind.GROUP:
            user = f"group:{p.neutrino_id}#member"
        elif p.kind == PrincipalKind.WORKSPACE_PUBLIC:
            user = f"workspace:{p.neutrino_id}#member"
        elif p.kind == PrincipalKind.TENANT_PUBLIC:
            user = f"tenant:{p.neutrino_id}#member"
        else:
            # Defensive — Principal validates the enum so unreachable in
            # practice. Silent skip is default-deny.
            continue
        out.append(
            ClientTuple(user=user, relation="viewer", object=f"doc:{doc_id}")
        )
    return out


def _bulk_grant_result(
    status: str,
    *,
    processed: int = 0,
    written: int = 0,
    existing: int = 0,
    failed: int = 0,
) -> dict:
    """Shape the bulk_grant_access result dict."""
    return {
        "status": status,
        "processed": processed,
        "written": written,
        "existing": existing,
        "failed": failed,
    }


class DocAclService:
    def __init__(
        self,
        *,
        session_factory=None,
        api_url: str | None = None,
        api_token: str | None = None,
        store_name_prefix: str | None = None,
        logger=None,
    ):
        """Document ACL client, shared by connector-service and ES-Ingestion.

        neutrino_database owns no database session and no service settings, so
        both arrive from the caller. ``session_factory`` is the async context
        manager each service already has (connector-service's get_db_context);
        it is required only by the store-registry path added in Task A4, so it
        stays optional for callers that never resolve a store.
        """
        self._session_factory = session_factory
        self.api_url = api_url or os.environ["OPENFGA_API_URL"]
        self.api_token = api_token or os.environ.get("OPENFGA_API_TOKEN") or None
        self.store_name_prefix = (
            store_name_prefix
            or os.environ.get("OPENFGA_STORE_NAME_PREFIX")
            or "neutrino-workspace"
        )
        self.logger = logger or logging.getLogger(__name__)

    def _fga_credentials(self) -> Credentials | None:
        """SDK credentials from ``api_token``, or None when unset.

        NC-494 — both file-permission services previously hardcoded
        ``credentials=_fga_credentials()`` and never read the token at all, while the gateway
        authenticates via ``build_fga_credentials``. Against a token-protected
        OpenFGA that meant every document-ACL call (grant, revoke, check,
        list_user_docs) failed with 401 while tenant RBAC kept working — file
        permissions silently inoperative. Unset (local dev) still means
        unauthenticated, exactly as before.
        """
        if not self.api_token:
            return None
        return Credentials(
            method="api_token",
            configuration=CredentialConfiguration(api_token=self.api_token),
        )

    def _get_store_name(self, workspace_id: str) -> str:
        """Generate store name: {workspace_id}_file_permissions"""
        return f"{workspace_id}_file_permissions"

    def _get_fga_client(self, store_id: str, model_id: str) -> OpenFgaClient:
        """Create an OpenFGA client bound to a store + model."""
        config = ClientConfiguration(
            api_url=self.api_url,
            store_id=store_id,
            authorization_model_id=model_id,
            credentials=self._fga_credentials(),
        )
        return OpenFgaClient(config)

    def _get_base_client(self, store_id: str = None) -> OpenFgaClient:
        """Create an OpenFGA client (optionally bound to a store)."""
        config = ClientConfiguration(
            api_url=self.api_url,
            store_id=store_id,
            credentials=self._fga_credentials(),
        )
        return OpenFgaClient(config)

    async def _find_store_by_name(self, store_name: str) -> str | None:
        """Find a store by name, returns store_id if found.

        Pages through list_stores via the continuation token — without
        passing it back in, an env with more than one page of stores only
        ever sees page 1, the store looks "missing", and
        _get_or_create_store creates a DUPLICATE store with the same name.
        """
        async with self._get_base_client() as client:
            continuation_token = None
            while True:
                options = (
                    {"continuation_token": continuation_token}
                    if continuation_token
                    else None
                )
                response = await client.list_stores(options=options)
                for store in response.stores:
                    if store.name == store_name:
                        return store.id

                continuation_token = response.continuation_token
                if not continuation_token:
                    break
        return None

    async def _get_latest_model_id(self, store_id: str) -> str | None:
        """Get the latest authorization model ID for a store."""
        async with self._get_base_client(store_id) as client:
            response = await client.read_authorization_models()
            if response.authorization_models:
                # Models are returned in reverse chronological order (latest first)
                return response.authorization_models[0].id
        return None

    async def _get_or_create_store(self, workspace_id: str) -> tuple[str, str] | None:
        """Get or create the OpenFGA store for a workspace.

        Returns:
            Tuple of (store_id, model_id) or None if failed
        """
        store_name = self._get_store_name(workspace_id)

        # Try to find existing store
        store_id = await self._find_store_by_name(store_name)

        if store_id:
            # Store exists, get latest model
            model_id = await self._get_latest_model_id(store_id)
            if model_id:
                # NC-113-a — lazy drift-heal: converge a store left on a stale
                # model (runtime net complementing the deploy migrator).
                model_id = await self._heal_store_model_if_stale(store_id, model_id)
                return store_id, model_id
            # Store exists but no model - create one
            model_id = await self._create_authorization_model(store_id)
            return store_id, model_id

        # Store doesn't exist - create store and model
        store_id = await self._create_store(store_name)
        if not store_id:
            return None
        model_id = await self._create_authorization_model(store_id)
        if not model_id:
            return None

        return store_id, model_id

    async def _create_store(self, store_name: str) -> str | None:
        """Create an OpenFGA store."""
        try:
            async with self._get_base_client() as client:
                body = CreateStoreRequest(name=store_name)
                response = await client.create_store(body)
                self.logger.info(f"Created file permissions store '{store_name}' with ID: {response.id}")
                return response.id
        except Exception as e:
            self.logger.error(f"Failed to create store '{store_name}': {e}")
            return None

    async def _create_authorization_model(self, store_id: str) -> str | None:
        """Write the canonical authorization model (neutrino_database SSOT) to a
        store, returning the new model id.

        NC-113-a: the model is no longer a service-local ``openfga_model.json``
        — connector-service and ES-Ingestion load the SAME model so they can
        never diverge (that divergence is what 400'd canonical viewer writes).
        """
        try:
            async with self._get_base_client(store_id) as client:
                response = await client.write_authorization_model(load_model())
                self.logger.info(
                    f"Created file permissions model with ID: {response.authorization_model_id}"
                )
                return response.authorization_model_id
        except Exception as e:
            self.logger.error(f"Failed to create authorization model for store {store_id}: {e}")
            return None

    async def _get_latest_model(self, store_id: str) -> dict | None:
        """Return the store's latest authorization model as a dict (or None)."""
        async with self._get_base_client(store_id) as client:
            response = await client.read_authorization_models()
            if response.authorization_models:
                return response.authorization_models[0].to_dict()
        return None

    async def _heal_store_model_if_stale(self, store_id: str, model_id: str) -> str:
        """Converge a store onto the canonical model if its deployed model is
        stale (NC-113-a lazy drift-heal).

        Returns the model id to use — the new one if a heal wrote it, else the
        passed-in current id. Process-cached; fail-soft (a heal error logs and
        falls back to the current id; the deploy migrator is the backstop).
        """
        if store_id in _HEALED_STORES:
            return model_id
        try:
            deployed = await self._get_latest_model(store_id)
            if deployed is not None and model_hash(deployed) == SOURCE_MODEL_HASH:
                _HEALED_STORES.add(store_id)
                return model_id
            new_model_id = await self._create_authorization_model(store_id)
            if new_model_id:
                self.logger.info(
                    f"[fga-heal] store {store_id} was on a stale model; "
                    f"wrote canonical model {new_model_id}"
                )
                _HEALED_STORES.add(store_id)
                return new_model_id
            return model_id
        except Exception as e:
            self.logger.warning(f"[fga-heal] drift check failed for store {store_id}: {e}")
            return model_id

    async def migrate_store_model(self, workspace_id: str) -> bool:
        """Create a new authorization model version for an existing store.

        This is needed when the model schema changes (e.g., adding wildcard support).
        The new model will be used for all subsequent operations.

        Args:
            workspace_id: Workspace ID whose store should be migrated

        Returns:
            True if migration succeeded, False otherwise
        """
        try:
            store_name = self._get_store_name(workspace_id)
            store_id = await self._find_store_by_name(store_name)

            if not store_id:
                self.logger.warning(f"[migrate_store_model] No store found for workspace {workspace_id}")
                return False

            # Create a new model version from the canonical neutrino_database model
            new_model_id = await self._create_authorization_model(store_id)
            if not new_model_id:
                self.logger.error(
                    f"[migrate_store_model] Failed to create new model for workspace {workspace_id}"
                )
                return False

            self.logger.info(
                f"[migrate_store_model] Successfully migrated store for workspace {workspace_id} "
                f"to new model {new_model_id}"
            )
            return True

        except Exception as e:
            self.logger.error(
                f"[migrate_store_model] Failed to migrate store for workspace {workspace_id}: {e}"
            )
            return False

    def _validate_ids(
        self, doc_ids: list[str] = None, user_ids: list[str] = None
    ) -> tuple[bool, str]:
        """Validate that IDs are not empty or whitespace-only."""
        if doc_ids is not None:
            if not doc_ids:
                return False, "doc_ids cannot be empty"
            for doc_id in doc_ids:
                if not doc_id or not doc_id.strip():
                    return False, "doc_id cannot be empty or whitespace"

        if user_ids is not None:
            if not user_ids:
                return False, "user_ids cannot be empty"
            for user_id in user_ids:
                if not user_id or not user_id.strip():
                    return False, "user_id cannot be empty or whitespace"

        return True, ""

    # ─────────────────────────────────────────────────────────────────
    # Permission Management
    # ─────────────────────────────────────────────────────────────────

    async def _write_tuples(
        self, client: OpenFgaClient, tuples: list[ClientTuple], model_id: str
    ) -> tuple[int, int, int]:
        """
        Write tuples to OpenFGA, handling duplicates gracefully.
        Writes one at a time to handle duplicates individually.

        Every tuple lands in exactly one bucket: written / duplicate /
        failed. Duplicates are business-as-usual (grants are idempotent);
        anything else is a REAL write failure the caller must be able to
        see — the old shape folded failures into the duplicate count, so
        genuine FGA write errors were invisible.

        Returns:
            Tuple of (new_count, existing_count, failed_count)
        """
        options = {"authorization_model_id": model_id}
        new_count = 0
        existing_count = 0
        failed_count = 0

        for t in tuples:
            try:
                body = ClientWriteRequest(writes=[t])
                await client.write(body, options)
                new_count += 1
            except Exception as e:
                # Check if it's a duplicate tuple error
                if "cannot write a tuple" in str(e).lower() or "already exists" in str(e).lower():
                    existing_count += 1
                    self.logger.debug(f"Tuple already exists: {t.object} -> {t.user}")
                else:
                    self.logger.warning(f"Failed to write tuple {t.object} -> {t.user}: {e}")
                    failed_count += 1

        return new_count, existing_count, failed_count

    async def _delete_tuples(
        self, client: OpenFgaClient, tuples: list[ClientTuple], model_id: str
    ) -> tuple[int, int, int]:
        """
        Delete tuples from OpenFGA, handling non-existent tuples gracefully.

        Only a genuine not-found counts as "not_found" — any other delete
        error lands in ``failed_count`` so callers can fail closed instead
        of reporting a revoke that never happened.

        Returns:
            Tuple of (deleted_count, not_found_count, failed_count)
        """
        options = {"authorization_model_id": model_id}
        deleted_count = 0
        not_found_count = 0
        failed_count = 0

        for t in tuples:
            try:
                body = ClientWriteRequest(deletes=[t])
                await client.write(body, options)
                deleted_count += 1
            except Exception as e:
                # Check if it's a not-found error
                obj = getattr(t, "object", t)
                user = getattr(t, "user", "?")
                if "cannot delete" in str(e).lower() or "does not exist" in str(e).lower():
                    not_found_count += 1
                    self.logger.debug(f"Tuple not found: {obj} -> {user}")
                else:
                    self.logger.warning(f"Failed to delete tuple {obj} -> {user}: {e}")
                    failed_count += 1

        return deleted_count, not_found_count, failed_count

    async def grant_access(self, workspace_id: str, doc_id: str, user_id: str) -> bool:
        """Grant a user access to a single document."""
        try:
            store_info = await self._get_or_create_store(workspace_id)
            if not store_info:
                self.logger.warning(
                    f"Failed to get/create file permissions store for workspace {workspace_id}"
                )
                return False

            store_id, model_id = store_info
            client = self._get_fga_client(store_id, model_id)
            async with client:
                tuple_key = ClientTuple(
                    user=f"user:{user_id}",
                    relation="can_access",
                    object=f"doc:{doc_id}",
                )
                new_count, existing_count, failed_count = await self._write_tuples(
                    client, [tuple_key], model_id
                )

                if failed_count > 0:
                    self.logger.error(
                        f"Failed to grant access to doc:{doc_id} for user:{user_id}"
                    )
                    return False
                if new_count > 0:
                    self.logger.info(f"Granted access to doc:{doc_id} for user:{user_id}")
                else:
                    self.logger.info(f"Permission already exists: doc:{doc_id} for user:{user_id}")
                return True
        except Exception as e:
            self.logger.error(f"Failed to grant access: {e}")
            return False

    async def grant_access_batch(self, workspace_id: str, doc_ids: list[str], user_id: str) -> int:
        """
        Grant a user access to multiple documents.

        Returns:
            Number of documents processed, or -1 on error (including any
            individual tuple write failing), -2 on validation error
        """
        is_valid, error_msg = self._validate_ids(doc_ids=doc_ids, user_ids=[user_id])
        if not is_valid:
            self.logger.warning(f"[grant_access_batch] Validation failed: {error_msg}")
            return -2

        try:
            store_info = await self._get_or_create_store(workspace_id)
            if not store_info:
                self.logger.warning(
                    f"Failed to get/create file permissions store for workspace {workspace_id}"
                )
                return -1

            store_id, model_id = store_info
            client = self._get_fga_client(store_id, model_id)
            async with client:
                tuples = [
                    ClientTuple(
                        user=f"user:{user_id}",
                        relation="can_access",
                        object=f"doc:{doc_id}",
                    )
                    for doc_id in doc_ids
                ]

                new_count, existing_count, failed_count = await self._write_tuples(
                    client, tuples, model_id
                )

                if failed_count > 0:
                    self.logger.error(
                        f"[grant_access_batch] {failed_count} tuple writes FAILED for "
                        f"user:{user_id} in workspace {workspace_id} "
                        f"(written={new_count}, existing={existing_count})"
                    )
                    return -1
                self.logger.info(
                    f"Granted access to {new_count} new documents for user:{user_id} "
                    f"in workspace {workspace_id} ({existing_count} already existed)"
                )
                return len(doc_ids)
        except Exception as e:
            self.logger.error(f"Failed to grant batch access: {e}")
            return -1

    async def bulk_grant_access(self, workspace_id: str, docs: list[dict]) -> dict:
        """
        Grant access for multiple documents with multiple users each.

        Returns a dict (was an int with -1/-2 sentinels — those masked
        per-tuple write failures, which callers could never see):
            - status: 'success' | 'partial_failure' | 'error' |
              'validation_error'
            - processed: tuples attempted
            - written / existing / failed: per-tuple outcome counts

        ``failed > 0`` is the signal callers must surface — those tuples
        are NOT in FGA and the affected users cannot see the docs.
        """
        if not docs:
            self.logger.warning("[bulk_grant_access] Validation failed: docs cannot be empty")
            return _bulk_grant_result("validation_error")

        for doc in docs:
            is_valid, error_msg = self._validate_ids(
                doc_ids=[doc.get("doc_id", "")], user_ids=doc.get("user_id", [])
            )
            if not is_valid:
                self.logger.warning(f"[bulk_grant_access] Validation failed: {error_msg}")
                return _bulk_grant_result("validation_error")

        try:
            store_info = await self._get_or_create_store(workspace_id)
            if not store_info:
                self.logger.warning(
                    f"Failed to get/create file permissions store for workspace {workspace_id}"
                )
                return _bulk_grant_result("error")

            store_id, model_id = store_info
            client = self._get_fga_client(store_id, model_id)
            async with client:
                tuples = []
                for doc in docs:
                    doc_id = doc["doc_id"]
                    user_ids = doc["user_id"]
                    for user_id in user_ids:
                        tuples.append(
                            ClientTuple(
                                user=f"user:{user_id}",
                                relation="can_access",
                                object=f"doc:{doc_id}",
                            )
                        )

                new_count, existing_count, failed_count = await self._write_tuples(
                    client, tuples, model_id
                )

                if failed_count > 0:
                    self.logger.error(
                        f"[bulk_grant_access] {failed_count} of {len(tuples)} tuple writes "
                        f"FAILED across {len(docs)} documents in workspace {workspace_id} "
                        f"(written={new_count}, existing={existing_count})"
                    )
                else:
                    self.logger.info(
                        f"Bulk granted {new_count} new permissions across {len(docs)} documents "
                        f"in workspace {workspace_id} ({existing_count} already existed)"
                    )
                return _bulk_grant_result(
                    "partial_failure" if failed_count > 0 else "success",
                    processed=len(tuples),
                    written=new_count,
                    existing=existing_count,
                    failed=failed_count,
                )
        except Exception as e:
            self.logger.error(f"Failed to bulk grant access: {e}")
            return _bulk_grant_result("error")

    async def revoke_access(self, workspace_id: str, doc_id: str, user_id: str) -> bool:
        """Revoke a user's access to a document."""
        is_valid, error_msg = self._validate_ids(doc_ids=[doc_id], user_ids=[user_id])
        if not is_valid:
            self.logger.warning(f"[revoke_access] Validation failed: {error_msg}")
            return False

        try:
            store_info = await self._get_or_create_store(workspace_id)
            if not store_info:
                self.logger.warning(f"No file permissions store for workspace {workspace_id}")
                return False

            store_id, model_id = store_info
            client = self._get_fga_client(store_id, model_id)
            async with client:
                tuple_key = ClientTuple(
                    user=f"user:{user_id}",
                    relation="can_access",
                    object=f"doc:{doc_id}",
                )
                deleted_count, not_found_count, failed_count = await self._delete_tuples(
                    client, [tuple_key], model_id
                )

                if failed_count > 0:
                    self.logger.error(f"Failed to revoke access to doc:{doc_id} for user:{user_id}")
                    return False
                if deleted_count > 0:
                    self.logger.info(f"Revoked access to doc:{doc_id} for user:{user_id}")
                else:
                    self.logger.info(f"Permission already revoked: doc:{doc_id} for user:{user_id}")
                return True
        except Exception as e:
            self.logger.error(f"Failed to revoke access: {e}")
            return False

    async def check_access(self, workspace_id: str, doc_id: str, user_id: str) -> bool:
        """Check if a user can access a document."""
        self.logger.info(
            f"[check_access] START - workspace_id={workspace_id}, doc_id={doc_id}, user_id={user_id}"
        )
        try:
            store_info = await self._get_or_create_store(workspace_id)
            if not store_info:
                self.logger.warning(
                    f"[check_access] No file permissions store for workspace {workspace_id}"
                )
                return False

            store_id, model_id = store_info
            client = self._get_fga_client(store_id, model_id)
            async with client:
                body = ClientCheckRequest(
                    user=f"user:{user_id}",
                    relation="can_access",
                    object=f"doc:{doc_id}",
                )
                options = {"authorization_model_id": model_id}
                response = await client.check(body, options)
                allowed = bool(response.allowed)
                self.logger.info(
                    f"[check_access] RESULT - user:{user_id} can_access doc:{doc_id} = {allowed}"
                )
                return allowed
        except Exception as e:
            self.logger.error(f"[check_access] FAILED - error={e}")
            return False

    async def _ensure_workspace_membership(
        self, client: OpenFgaClient, workspace_id: str, member_id: str
    ) -> None:
        """Lazy-materialize the ``workspace:<ws>#member @ user:<member_id>``
        bridge tuple in Store B.

        The canonical orchestrator writes doc viewers as
        ``workspace:<ws>#member`` (the WORKSPACE_PUBLIC principal — both
        the dev empty-ACL fallback AND any future prod public-in-workspace
        flow). For ``list_objects(can_access, user:<member_id>)`` to surface
        those docs, FGA needs the bridge tuple connecting member to
        workspace. Nothing in the codebase wrote this tuple historically —
        the workspace_member DB row landed in the gateway, OpenFGA Store A
        got admin tuples for tenant RBAC, and Store B (file ACLs) was never
        told about workspace membership. Allow-list silently returned 0
        for every member; chat short-circuited. TD-FGA-WORKSPACE-MEMBER-BRIDGE.

        Production pattern (Auth0 / Linear / Notion for the same shape):
        materialize-on-read. Cheap (one idempotent FGA write per /my-docs
        call, FGA itself dedupes), single-seam (vs sweeping 7 gateway
        workspace_member insert sites), self-heals if the store is ever
        recreated, no gateway↔Store-B coupling.

        Fail-soft: if the write blips, swallow and let list_objects proceed.
        The user will retry on next chat turn; FGA is off the critical path.
        """
        try:
            write_body = ClientWriteRequest(
                writes=[
                    ClientTuple(
                        user=f"user:{member_id}",
                        relation="member",
                        object=f"workspace:{workspace_id}",
                    )
                ]
            )
            await client.write(write_body)
        except Exception as e:
            self.logger.warning(
                "[ensure_workspace_membership] write failed (idempotent retry "
                "on next call) - workspace=%s member=%s err=%s",
                workspace_id, member_id, e,
            )

    async def list_user_docs(self, workspace_id: str, user_id: str) -> list[str]:
        """List all documents a user can access."""
        try:
            store_info = await self._get_or_create_store(workspace_id)
            if not store_info:
                return []

            store_id, model_id = store_info
            client = self._get_fga_client(store_id, model_id)
            async with client:
                if user_id is None:
                    body = ClientListObjectsRequest(
                        user="user:*",
                        relation="can_access",
                        type="doc",
                    )

                else:
                    await self._ensure_workspace_membership(
                        client, workspace_id, user_id
                    )
                    body = ClientListObjectsRequest(
                        user=f"user:{user_id}",
                        relation="can_access",
                        type="doc",
                    )
                options = {"authorization_model_id": model_id}
                response = await client.list_objects(body, options)
                doc_ids = []
                for obj in response.objects:
                    if obj.startswith("doc:"):
                        doc_ids.append(obj.split(":", 1)[1])
                return doc_ids
        except Exception as e:
            self.logger.error(f"Failed to list user docs: {e}")
            return []

    async def _list_doc_direct_users(
        self, workspace_id: str, doc_id: str
    ) -> tuple[bool, list[str]]:
        """Internal: List direct user permissions and check if file is published.

        This returns only direct user:xxx tuples, not workspace users.
        Used by sync_doc_permissions to compare only direct permissions.

        Args:
            workspace_id: Workspace ID
            doc_id: Document ID

        Returns:
            Tuple of (is_public, direct_user_ids)
        """
        try:
            store_info = await self._get_or_create_store(workspace_id)
            if not store_info:
                return False, []

            store_id, model_id = store_info
            async with self._get_base_client(store_id) as client:
                body = ReadRequestTupleKey(
                    object=f"doc:{doc_id}",
                    relation="can_access",
                )

                direct_user_ids = []
                is_public = False
                continuation_token = None

                while True:
                    options = (
                        {"continuation_token": continuation_token} if continuation_token else None
                    )
                    response = await client.read(body, options)

                    for t in response.tuples:
                        user = t.key.user
                        if user == "user:*":
                            is_public = True
                        elif user.startswith("user:"):
                            direct_user_ids.append(user.split(":", 1)[1])

                    continuation_token = response.continuation_token
                    if not continuation_token:
                        break

                return is_public, direct_user_ids

        except Exception as e:
            self.logger.error(f"Failed to list direct doc users for doc {doc_id}: {e}")
            return False, []

    async def list_doc_users(
        self, workspace_id: str, doc_id: str, tenant_id: str | None = None
    ) -> dict:
        """List all users who have access to a document.

        If the document is published (has user:* wildcard), fetches all active
        tenant users from APP_DB and returns them along with is_public=True.

        Args:
            workspace_id: Workspace ID
            doc_id: Document ID
            tenant_id: Tenant ID — required to expand a published file into
                the full tenant user list (``get_all_tenant_user_ids``
                queries ``"user".tenant_id``; passing workspace_id there
                matches nothing / the wrong tenant). Callers thread it
                through from ``request.state.tenant_id``.

        Returns:
            dict with:
            - is_public: bool - True if file is published (has user:* access)
            - user_ids: List[str] - All users with access (all tenant users if published)
        """
        from app.services.user_mapping_service import get_all_tenant_user_ids

        result = {
            "is_public": False,
            "user_ids": []
        }

        try:
            is_public, direct_user_ids = await self._list_doc_direct_users(workspace_id, doc_id)
            result["is_public"] = is_public

            if is_public:
                # File is published - get all active tenant users from APP_DB
                if tenant_id:
                    all_tenant_users = await get_all_tenant_user_ids(tenant_id)
                else:
                    self.logger.warning(
                        f"[list_doc_users] doc:{doc_id} is published but no tenant_id "
                        f"was provided; returning direct permissions only"
                    )
                    all_tenant_users = []
                # Merge with direct user IDs (in case there are direct permissions too)
                # Using set to deduplicate
                all_user_ids = set(all_tenant_users) | set(direct_user_ids)
                result["user_ids"] = list(all_user_ids)
            else:
                # File is not published - return only direct user permissions
                result["user_ids"] = direct_user_ids

            return result

        except Exception as e:
            self.logger.error(f"Failed to list doc users for doc {doc_id}: {e}")
            return result

    async def bulk_revoke_access(self, workspace_id: str, docs: list[dict]) -> int:
        """
        Revoke access for multiple documents with multiple users each.

        Args:
            workspace_id: Workspace ID
            docs: List of dicts with 'doc_id' and 'user_id' (list of user IDs to revoke)

        Returns:
            Total tuples deleted, 0 when deletes failed (fail closed),
            -1 on store/transport error, -2 on validation error
        """
        if not docs:
            self.logger.warning("[bulk_revoke_access] Validation failed: docs cannot be empty")
            return -2

        for doc in docs:
            user_ids = doc.get("user_id", [])
            if user_ids:  # Only validate if there are users to revoke
                is_valid, error_msg = self._validate_ids(
                    doc_ids=[doc.get("doc_id", "")], user_ids=user_ids
                )
                if not is_valid:
                    self.logger.warning(f"[bulk_revoke_access] Validation failed: {error_msg}")
                    return -2

        try:
            store_info = await self._get_or_create_store(workspace_id)
            if not store_info:
                self.logger.warning(
                    f"Failed to get/create file permissions store for workspace {workspace_id}"
                )
                return -1

            store_id, model_id = store_info
            client = self._get_fga_client(store_id, model_id)
            async with client:
                tuples = []
                for doc in docs:
                    doc_id = doc["doc_id"]
                    user_ids = doc.get("user_id", [])
                    for user_id in user_ids:
                        tuples.append(
                            ClientTuple(
                                user=f"user:{user_id}",
                                relation="can_access",
                                object=f"doc:{doc_id}",
                            )
                        )

                if not tuples:
                    return 0

                deleted_count, not_found_count, failed_count = await self._delete_tuples(
                    client, tuples, model_id
                )

                if failed_count > 0:
                    self.logger.error(
                        "[bulk_revoke_access] %d tuple deletes FAILED in workspace %s; "
                        "reporting failure rather than success",
                        failed_count,
                        workspace_id,
                    )
                    return 0

                self.logger.info(
                    f"Bulk revoked {deleted_count} permissions across {len(docs)} documents "
                    f"in workspace {workspace_id} ({not_found_count} not found)"
                )
                return deleted_count
        except Exception as e:
            self.logger.error(f"Failed to bulk revoke access: {e}")
            return -1

    async def revoke_all_doc_tuples(self, workspace_id: str, doc_id: str) -> int:
        """Delete EVERY tuple stored on ``doc:{doc_id}`` — the cascade-delete
        primitive.

        The old cascade path (list_doc_users → bulk_revoke_access) only
        covered direct ``can_access`` user tuples: ``viewer`` tuples
        (written by replace_viewer_tuples / replicate_file_acl — including
        workspace:{ws}#member and group:{g}#member grants) and the
        ``user:*`` publish wildcard were never deleted, so a deleted doc
        stayed authorized in FGA forever. It also expanded a published doc
        to every active workspace user and issued one delete per user for
        tuples that mostly didn't exist (O(workspace) no-op calls).

        This instead reads what is ACTUALLY stored — one paginated read per
        relation in _DOC_RELATIONS — and deletes exactly that via atomic
        ``client.write(deletes=…)`` batches (each batch either fully
        applies or fully rolls back, mirroring replace_viewer_tuples).

        Returns the number of tuples deleted. RAISES on failure — unlike
        most methods here — because the delete cascade must hard-abort
        (500, no tombstone) when FGA can't be cleaned: a tombstoned row
        that FGA still authorizes is the worst possible state.
        """
        store_info = await self._get_or_create_store(workspace_id)
        if not store_info:
            raise RuntimeError(
                f"[revoke_all_doc_tuples] no file permissions store for "
                f"workspace {workspace_id}"
            )
        store_id, model_id = store_info

        # 1. Read every tuple on the object (paginate via continuation token).
        tuples_to_delete: list[ClientTuple] = []
        async with self._get_base_client(store_id) as client:
            for relation in _DOC_RELATIONS:
                body = ReadRequestTupleKey(
                    object=f"doc:{doc_id}", relation=relation
                )
                continuation_token: str | None = None
                while True:
                    options = (
                        {"continuation_token": continuation_token}
                        if continuation_token
                        else None
                    )
                    response = await client.read(body, options)
                    for t in response.tuples:
                        tuples_to_delete.append(
                            ClientTuple(
                                user=t.key.user,
                                relation=relation,
                                object=f"doc:{doc_id}",
                            )
                        )
                    continuation_token = response.continuation_token
                    if not continuation_token:
                        break

        if not tuples_to_delete:
            self.logger.info(
                f"[revoke_all_doc_tuples] doc={doc_id} workspace={workspace_id} "
                f"had no tuples to delete"
            )
            return 0

        # 2. ATOMIC delete batches — mirror replace_viewer_tuples' write
        # shape. Deleting exactly what the read returned means zero no-op
        # delete calls, regardless of publish state.
        client = self._get_fga_client(store_id, model_id)
        async with client:
            for batch in _chunks(tuples_to_delete, _WRITE_BATCH_SIZE):
                body = ClientWriteRequest(deletes=batch)
                await client.write(body, {"authorization_model_id": model_id})

        self.logger.info(
            f"[revoke_all_doc_tuples] doc={doc_id} workspace={workspace_id} "
            f"deleted={len(tuples_to_delete)} tuples"
        )
        return len(tuples_to_delete)

    async def sync_doc_permissions(
        self, workspace_id: str, doc_id: str, new_user_ids: list[str]
    ) -> dict:
        """
        Sync permissions for a document by comparing current permissions with new ones.
        Grants access to new users and revokes access from users no longer in the list.

        Args:
            workspace_id: Workspace ID
            doc_id: Document ID
            new_user_ids: List of user IDs that should have access

        Returns:
            dict with 'granted', 'revoked', 'unchanged' counts and 'status'
        """
        result = {
            "granted": 0,
            "revoked": 0,
            "unchanged": 0,
            "status": "success",
            "error": None,
        }

        try:
            # Get current direct user permissions (excludes workspace users from published files)
            # This ensures sync only affects direct permissions, not publish status
            is_published, current_user_ids = await self._list_doc_direct_users(workspace_id, doc_id)
            current_set = set(current_user_ids)
            new_set = set(new_user_ids)

            if is_published:
                self.logger.info(
                    f"[sync_doc_permissions] doc={doc_id} is published, "
                    f"syncing only direct permissions (publish status preserved)"
                )

            # Calculate differences
            users_to_grant = new_set - current_set
            users_to_revoke = current_set - new_set
            unchanged = current_set & new_set

            result["unchanged"] = len(unchanged)

            self.logger.info(
                f"[sync_doc_permissions] doc={doc_id}: "
                f"current={len(current_set)}, new={len(new_set)}, "
                f"to_grant={len(users_to_grant)}, to_revoke={len(users_to_revoke)}"
            )

            # Grant access to new users
            if users_to_grant:
                store_info = await self._get_or_create_store(workspace_id)
                if store_info:
                    store_id, model_id = store_info
                    client = self._get_fga_client(store_id, model_id)
                    async with client:
                        tuples = [
                            ClientTuple(
                                user=f"user:{user_id}",
                                relation="can_access",
                                object=f"doc:{doc_id}",
                            )
                            for user_id in users_to_grant
                        ]
                        new_count, existing_count, failed_count = await self._write_tuples(
                            client, tuples, model_id
                        )
                        result["granted"] = new_count
                        if failed_count > 0:
                            self.logger.error(
                                f"[sync_doc_permissions] doc={doc_id}: "
                                f"{failed_count} grant writes FAILED"
                            )
                            result["status"] = "error"
                            result["error"] = f"{failed_count} grant writes failed"

            # Revoke access from removed users
            if users_to_revoke:
                store_info = await self._get_or_create_store(workspace_id)
                if store_info:
                    store_id, model_id = store_info
                    client = self._get_fga_client(store_id, model_id)
                    async with client:
                        tuples = [
                            ClientTuple(
                                user=f"user:{user_id}",
                                relation="can_access",
                                object=f"doc:{doc_id}",
                            )
                            for user_id in users_to_revoke
                        ]
                        deleted_count, not_found_count, failed_count = await self._delete_tuples(
                            client, tuples, model_id
                        )
                        result["revoked"] = deleted_count
                        if failed_count > 0:
                            result["status"] = "error"
                            result["error"] = f"{failed_count} revoke deletes failed"

            self.logger.info(
                f"[sync_doc_permissions] doc={doc_id}: "
                f"granted={result['granted']}, revoked={result['revoked']}, "
                f"unchanged={result['unchanged']}"
            )

        except Exception as e:
            self.logger.error(f"Failed to sync permissions for doc {doc_id}: {e}")
            result["status"] = "error"
            result["error"] = str(e)

        return result

    # ─────────────────────────────────────────────────────────────────
    # File Publishing (Tenant-wide access)
    # ─────────────────────────────────────────────────────────────────

    async def publish_file(self, workspace_id: str, doc_id: str) -> bool:
        """Make a file public within the workspace by adding user:* (wildcard) access.

        This grants access to all users in the workspace's OpenFGA store.
        Individual user permissions are preserved alongside public access.

        Args:
            workspace_id: Workspace ID
            doc_id: Document ID to publish

        Returns:
            True if published successfully, False otherwise
        """
        is_valid, error_msg = self._validate_ids(doc_ids=[doc_id])
        if not is_valid:
            self.logger.warning(f"[publish_file] Validation failed: {error_msg}")
            return False

        try:
            store_info = await self._get_or_create_store(workspace_id)
            if not store_info:
                self.logger.warning(
                    f"[publish_file] Failed to get/create store for workspace {workspace_id}"
                )
                return False

            store_id, model_id = store_info
            client = self._get_fga_client(store_id, model_id)
            async with client:
                # Create tuple with user:* wildcard for public access
                tuple_key = ClientTuple(
                    user="user:*",
                    relation="can_access",
                    object=f"doc:{doc_id}",
                )
                new_count, existing_count, failed_count = await self._write_tuples(
                    client, [tuple_key], model_id
                )

                if failed_count > 0:
                    self.logger.error(
                        f"[publish_file] Failed to publish doc:{doc_id} "
                        f"in workspace {workspace_id}"
                    )
                    return False
                if new_count > 0:
                    self.logger.info(
                        f"[publish_file] Published doc:{doc_id} in workspace {workspace_id}"
                    )
                else:
                    self.logger.info(
                        f"[publish_file] doc:{doc_id} was already published in workspace {workspace_id}"
                    )
                return True

        except Exception as e:
            self.logger.error(f"[publish_file] Failed to publish doc {doc_id}: {e}")
            return False

    async def unpublish_file(self, workspace_id: str, doc_id: str) -> bool:
        """Remove public access from a file (individual permissions remain).

        This removes the user:* wildcard tuple, but keeps specific user permissions.

        Args:
            workspace_id: Workspace ID
            doc_id: Document ID to unpublish

        Returns:
            True if unpublished successfully, False otherwise
        """
        is_valid, error_msg = self._validate_ids(doc_ids=[doc_id])
        if not is_valid:
            self.logger.warning(f"[unpublish_file] Validation failed: {error_msg}")
            return False

        try:
            store_info = await self._get_or_create_store(workspace_id)
            if not store_info:
                self.logger.warning(f"[unpublish_file] No store for workspace {workspace_id}")
                return False

            store_id, model_id = store_info
            client = self._get_fga_client(store_id, model_id)
            async with client:
                # Delete tuple with user:* wildcard
                tuple_key = ClientTuple(
                    user="user:*",
                    relation="can_access",
                    object=f"doc:{doc_id}",
                )
                deleted_count, not_found_count, failed_count = await self._delete_tuples(
                    client, [tuple_key], model_id
                )

                if failed_count > 0:
                    self.logger.error(
                        f"[unpublish_file] Failed to unpublish doc:{doc_id} "
                        f"in workspace {workspace_id}"
                    )
                    return False
                if deleted_count > 0:
                    self.logger.info(
                        f"[unpublish_file] Unpublished doc:{doc_id} in workspace {workspace_id}"
                    )
                else:
                    self.logger.info(
                        f"[unpublish_file] doc:{doc_id} was not published in workspace {workspace_id}"
                    )
                return True

        except Exception as e:
            self.logger.error(f"[unpublish_file] Failed to unpublish doc {doc_id}: {e}")
            return False

    async def is_file_published(self, workspace_id: str, doc_id: str) -> bool:
        """Check if a file has public (user:*) access within the workspace.

        Args:
            workspace_id: Workspace ID
            doc_id: Document ID to check

        Returns:
            True if file is published (has user:* access), False otherwise
        """
        try:
            store_info = await self._get_or_create_store(workspace_id)
            if not store_info:
                return False

            store_id, model_id = store_info
            async with self._get_base_client(store_id) as client:
                # Read tuples for this document
                body = ReadRequestTupleKey(
                    object=f"doc:{doc_id}",
                    relation="can_access",
                )

                continuation_token = None
                while True:
                    options = (
                        {"continuation_token": continuation_token} if continuation_token else None
                    )
                    response = await client.read(body, options)

                    for t in response.tuples:
                        # Check for wildcard user
                        if t.key.user == "user:*":
                            return True

                    continuation_token = response.continuation_token
                    if not continuation_token:
                        break

                return False

        except Exception as e:
            self.logger.error(f"[is_file_published] Failed to check doc {doc_id}: {e}")
            return False

    async def batch_is_file_published(self, workspace_id: str, doc_ids: list[str]) -> dict:
        """Check public status for multiple files in a single store session.

        Reuses one OpenFGA client connection instead of calling is_file_published()
        individually for each file, which saves repeated store lookups.

        Args:
            workspace_id: Workspace ID
            doc_ids: List of document IDs to check

        Returns:
            Dict mapping file_id → is_public (bool). Defaults to False on error.
        """
        statuses = {doc_id: False for doc_id in doc_ids}
        try:
            store_info = await self._get_or_create_store(workspace_id)
            if not store_info:
                return statuses

            store_id, model_id = store_info
            async with self._get_base_client(store_id) as client:
                for doc_id in doc_ids:
                    try:
                        body = ReadRequestTupleKey(
                            object=f"doc:{doc_id}",
                            relation="can_access",
                        )
                        continuation_token = None
                        found = False
                        while True:
                            options = (
                                {"continuation_token": continuation_token}
                                if continuation_token
                                else None
                            )
                            response = await client.read(body, options)
                            for t in response.tuples:
                                if t.key.user == "user:*":
                                    statuses[doc_id] = True
                                    found = True
                                    break
                            if found:
                                break
                            continuation_token = response.continuation_token
                            if not continuation_token:
                                break
                    except Exception as e:
                        self.logger.error(f"[batch_is_file_published] Error checking doc {doc_id}: {e}")
            return statuses
        except Exception as e:
            self.logger.error(f"[batch_is_file_published] Failed for workspace {workspace_id}: {e}")
            return statuses


    # ─────────────────────────────────────────────────────────────────
    # CANON-DOC-4d — canonical viewer-set sync (idempotent dual-store-ready)
    # ─────────────────────────────────────────────────────────────────

    async def replace_viewer_tuples(
        self,
        workspace_id: str,
        doc_id: str,
        principals: list,
    ) -> dict:
        """Sync the doc's ``viewer`` tuples to exactly the resolved
        principal set (CANON-DOC-4d).

        Reads existing ``(doc:DOC_ID, viewer, *)`` tuples, computes
        diff vs the new set, writes adds, deletes removes. Idempotent
        — re-running with unchanged inputs produces zero writes (the
        load-bearing property for re-syncs).

        `principals` is a list of ResolvedPrincipal — the output of
        canonical/acl_resolver. The kind→user-string mapping happens
        via _build_viewer_tuples_for_doc.

        Returns ``{granted, revoked, unchanged, status, error}``.
        On store-lookup failure (FGA outage / misconfig) returns
        ``status='error'`` rather than raising — the indexer keeps
        moving; the audit log + next retry handle recovery.
        """
        result = {
            "granted": 0,
            "revoked": 0,
            "unchanged": 0,
            "status": "success",
            "error": None,
        }
        try:
            store_info = await self._get_or_create_store(workspace_id)
            if not store_info:
                self.logger.warning(
                    f"[replace_viewer_tuples] No store for workspace {workspace_id}"
                )
                result["status"] = "error"
                result["error"] = "store_lookup_failed"
                return result
            store_id, model_id = store_info

            # 1. Build the desired tuple set from the resolved principals.
            desired_tuples = _build_viewer_tuples_for_doc(
                doc_id=doc_id, principals=principals
            )
            desired_users = {t.user for t in desired_tuples}

            # 2. Read existing viewer tuples (paginate via continuation token).
            existing_users: set[str] = set()
            async with self._get_base_client(store_id) as client:
                body = ReadRequestTupleKey(
                    object=f"doc:{doc_id}", relation="viewer"
                )
                continuation_token: str | None = None
                while True:
                    options = (
                        {"continuation_token": continuation_token}
                        if continuation_token
                        else None
                    )
                    response = await client.read(body, options)
                    for t in response.tuples:
                        existing_users.add(t.key.user)
                    continuation_token = response.continuation_token
                    if not continuation_token:
                        break

            # 3. Diff.
            users_to_add = desired_users - existing_users
            users_to_remove = existing_users - desired_users
            unchanged = desired_users & existing_users
            result["unchanged"] = len(unchanged)

            # 4. ATOMIC write — Track F.0 / F4.
            #
            # Single client.write() call carrying BOTH the additions and
            # the deletions. OpenFGA's Write API is transactional by
            # default: either every tuple in the batch is applied or
            # none are. The previous shape made two separate API calls
            # (_write_tuples then _delete_tuples), each opening its own
            # client and iterating per-tuple. Between the calls — and
            # between iterations inside each helper — there was a
            # window where the doc's viewer set was a mixed half-state.
            # On flaky FGA, an outage between the two halves left the
            # tuple set permanently split (some new viewers granted,
            # some old viewers not revoked, or vice versa). One atomic
            # call collapses the window.
            add_tuples = (
                [t for t in desired_tuples if t.user in users_to_add]
                if users_to_add else []
            )
            remove_tuples = (
                [
                    ClientTuple(user=u, relation="viewer", object=f"doc:{doc_id}")
                    for u in users_to_remove
                ]
                if users_to_remove else []
            )

            if add_tuples or remove_tuples:
                client = self._get_fga_client(store_id, model_id)
                async with client:
                    body = ClientWriteRequest(
                        writes=add_tuples or None,
                        deletes=remove_tuples or None,
                    )
                    await client.write(
                        body, {"authorization_model_id": model_id}
                    )
                result["granted"] = len(add_tuples)
                result["revoked"] = len(remove_tuples)

            self.logger.info(
                f"[replace_viewer_tuples] doc={doc_id} workspace={workspace_id} "
                f"granted={result['granted']} revoked={result['revoked']} "
                f"unchanged={result['unchanged']}"
            )
            return result

        except Exception as e:
            self.logger.error(
                f"[replace_viewer_tuples] Failed for doc={doc_id} workspace={workspace_id}: {e}"
            )
            result["status"] = "error"
            result["error"] = str(e)
            return result

    async def replace_group_members(
        self,
        workspace_id: str,
        group_id: str,
        member_ids: list[str],
    ) -> dict:
        """Sync a group's membership tuples to exactly ``member_ids`` (NC-129).

        Writes ``user:<member_id> member group:<group_id>`` for the resolved
        members and deletes any that are no longer in the group. This is what
        makes a ``group:<gid>#member viewer doc`` grant actually resolve to
        people — a viewer tuple on an empty group grants access to nobody.

        Same read → diff → ATOMIC write shape as ``replace_viewer_tuples``:
        idempotent (a re-sync with unchanged membership writes nothing), and
        adds + deletes travel in one transactional ``client.write`` so the
        group's membership never sits in a half-applied state.

        Returns ``{granted, revoked, unchanged, status, error}``; on store
        lookup failure returns ``status='error'`` rather than raising.
        """
        result = {
            "granted": 0,
            "revoked": 0,
            "unchanged": 0,
            "status": "success",
            "error": None,
        }
        try:
            store_info = await self._get_or_create_store(workspace_id)
            if not store_info:
                self.logger.warning(
                    f"[replace_group_members] No store for workspace {workspace_id}"
                )
                result["status"] = "error"
                result["error"] = "store_lookup_failed"
                return result
            store_id, model_id = store_info

            desired_users = {f"user:{m}" for m in member_ids if m}

            # Read existing (group:GID, member, *) tuples (paginated).
            existing_users: set[str] = set()
            async with self._get_base_client(store_id) as client:
                body = ReadRequestTupleKey(
                    object=f"group:{group_id}", relation="member"
                )
                continuation_token: str | None = None
                while True:
                    options = (
                        {"continuation_token": continuation_token}
                        if continuation_token
                        else None
                    )
                    response = await client.read(body, options)
                    for t in response.tuples:
                        existing_users.add(t.key.user)
                    continuation_token = response.continuation_token
                    if not continuation_token:
                        break

            users_to_add = desired_users - existing_users
            users_to_remove = existing_users - desired_users
            result["unchanged"] = len(desired_users & existing_users)

            add_tuples = [
                ClientTuple(user=u, relation="member", object=f"group:{group_id}")
                for u in users_to_add
            ]
            remove_tuples = [
                ClientTuple(user=u, relation="member", object=f"group:{group_id}")
                for u in users_to_remove
            ]

            if add_tuples or remove_tuples:
                client = self._get_fga_client(store_id, model_id)
                async with client:
                    body = ClientWriteRequest(
                        writes=add_tuples or None,
                        deletes=remove_tuples or None,
                    )
                    await client.write(body, {"authorization_model_id": model_id})
                result["granted"] = len(add_tuples)
                result["revoked"] = len(remove_tuples)

            self.logger.info(
                f"[replace_group_members] group={group_id} workspace={workspace_id} "
                f"granted={result['granted']} revoked={result['revoked']} "
                f"unchanged={result['unchanged']}"
            )
            return result

        except Exception as e:
            self.logger.error(
                f"[replace_group_members] Failed for group={group_id} "
                f"workspace={workspace_id}: {e}"
            )
            result["status"] = "error"
            result["error"] = str(e)
            return result
