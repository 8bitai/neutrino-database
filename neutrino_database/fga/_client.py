"""openfga_sdk-backed implementation of the ``FgaAdminClient`` protocol.

Thin transport glue only — the migrate orchestration + drift logic lives in
``migrate.py`` and is unit-tested against a fake. This class is exercised
end-to-end by the dev-validation step (Phase 6), not unit tests, since it needs
a live OpenFGA.

Mirrors connector-service's client construction (``ClientConfiguration`` /
``OpenFgaClient``) so it speaks to the same stores the services do.
"""

from __future__ import annotations

from typing import Any

from openfga_sdk.client import ClientConfiguration, OpenFgaClient


class OpenFgaAdminClient:
    """Store-level admin surface: list stores, read a store's latest model,
    write a new model version to a store."""

    def __init__(self, api_url: str):
        self.api_url = api_url

    def _client(self, store_id: str | None = None) -> OpenFgaClient:
        return OpenFgaClient(
            ClientConfiguration(api_url=self.api_url, store_id=store_id, credentials=None)
        )

    async def list_store_ids(self) -> list[str]:
        ids: list[str] = []
        async with self._client() as client:
            continuation_token = None
            while True:
                response = await client.list_stores()
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
