"""openfga_sdk-backed implementation of the ``FgaAdminClient`` protocol.

Thin transport glue only — the migrate orchestration + drift logic lives in
``migrate.py`` and is unit-tested against a fake. This class is exercised
end-to-end by the dev-validation step (Phase 6), not unit tests, since it needs
a live OpenFGA.

Mirrors connector-service's client construction (``ClientConfiguration`` /
``OpenFgaClient``) so it speaks to the same stores the services do.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlsplit

from openfga_sdk.client import ClientConfiguration, OpenFgaClient
from openfga_sdk.credentials import CredentialConfiguration, Credentials

logger = logging.getLogger(__name__)

# Hosts for which plain HTTP is acceptable (local dev / in-cluster loopback).
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "[::1]", ""})


def _validate_api_url(api_url: str, *, allow_insecure_http: bool) -> None:
    """Fail closed (D-3) when talking to a non-local OpenFGA over plain HTTP.

    A remote OpenFGA reached over ``http://`` sends the store-admin traffic —
    and any API token — in cleartext. We require ``https`` for non-localhost
    hosts. ``allow_insecure_http=True`` (env escape hatch) downgrades the error
    to a warning for operators who terminate TLS at a trusted hop.
    """
    scheme = (urlsplit(api_url).scheme or "").lower()
    host = (urlsplit(api_url).hostname or "").lower()

    if scheme == "https":
        return
    if host in _LOCAL_HOSTS:
        return  # local dev over http is fine

    msg = (
        f"OpenFGA api_url {api_url!r} uses insecure scheme {scheme!r} to "
        f"non-local host {host!r}; use https. Set OPENFGA_ALLOW_INSECURE_HTTP=1 "
        f"to override (e.g. TLS terminated at a trusted proxy)."
    )
    if allow_insecure_http:
        logger.warning("[fga] %s (overridden by OPENFGA_ALLOW_INSECURE_HTTP)", msg)
        return
    raise ValueError(msg)


class OpenFgaAdminClient:
    """Store-level admin surface: list stores, read a store's latest model,
    write a new model version to a store.

    Auth (D-3): pass ``api_token`` to authenticate to a protected OpenFGA via a
    preshared key (``Authorization: Bearer <token>``). When ``api_token`` is
    None the client stays unauthenticated, preserving the local-dev default of
    an auth-disabled OpenFGA.
    """

    def __init__(
        self,
        api_url: str,
        *,
        api_token: str | None = None,
        allow_insecure_http: bool = False,
    ):
        _validate_api_url(api_url, allow_insecure_http=allow_insecure_http)
        self.api_url = api_url
        self._api_token = api_token

    def _credentials(self) -> Credentials | None:
        if not self._api_token:
            return None
        return Credentials(
            method="api_token",
            configuration=CredentialConfiguration(api_token=self._api_token),
        )

    def _client(self, store_id: str | None = None) -> OpenFgaClient:
        return OpenFgaClient(
            ClientConfiguration(
                api_url=self.api_url,
                store_id=store_id,
                credentials=self._credentials(),
            )
        )

    async def list_store_ids(self) -> list[str]:
        ids: list[str] = []
        async with self._client() as client:
            continuation_token = None
            while True:
                # Pass the continuation token back in — without it, an env with
                # more than one page of stores re-fetches page 1 forever.
                options = (
                    {"continuation_token": continuation_token}
                    if continuation_token
                    else None
                )
                response = await client.list_stores(options=options)
                ids.extend(s.id for s in response.stores)
                continuation_token = response.continuation_token
                if not continuation_token:
                    break
        return ids

    async def read_latest_model(self, store_id: str) -> dict[str, Any] | None:
        async with self._client(store_id) as client:
            response = await client.read_authorization_models()
            models = response.authorization_models
            if not models:
                return None
            # Latest first (reverse chronological), per OpenFGA contract.
            return models[0].to_dict()

    async def write_model(self, store_id: str, model: dict[str, Any]) -> str:
        async with self._client(store_id) as client:
            response = await client.write_authorization_model(model)
            return response.authorization_model_id
