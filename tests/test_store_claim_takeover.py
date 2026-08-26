"""A store claim whose creator died must not brick the workspace.

``_get_or_create_store`` inserts a claim row with ``store_id IS NULL`` before
calling CreateStore, so only one caller reaches OpenFGA. If that caller is
killed between the insert and the fill update, the row stays unfilled: every
later caller loses the insert, polls ``_await_store_row`` to timeout, and gets
None. The workspace's document permissions stay dead until someone runs SQL by
hand, and the backfill skips the row too because it uses ON CONFLICT DO NOTHING.

The window is widest during a deploy, which is exactly when processes restart.

``_take_over_stale_claim`` reclaims a row older than
``_STORE_CLAIM_STALE_SECONDS``. The UPDATE is the lock: it matches only while
``created_at`` is still stale, and the winner refreshes it in the same
statement, so two concurrent takers cannot both win.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from neutrino_database.fga import doc_acl
from neutrino_database.fga.doc_acl import DocAclService


class _Updated:
    """Stands in for the UPDATE result: rowcount says whether we claimed it."""

    def __init__(self, rowcount: int):
        self.rowcount = rowcount


class _Session:
    def __init__(self, rowcount: int):
        self._rowcount = rowcount
        self.updates = 0
        self.commits = 0

    async def execute(self, stmt):
        self.updates += 1
        return _Updated(self._rowcount)

    async def commit(self):
        self.commits += 1

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


@pytest.fixture
def service():
    # No api_url and no OPENFGA_API_URL needed: the constructor defaults.
    return DocAclService()


async def test_a_stale_claim_is_taken_over(service):
    session = _Session(rowcount=1)

    assert await service._take_over_stale_claim(session, "ws-1") is True
    assert session.commits == 1


async def test_a_fresh_claim_is_left_alone(service):
    """The winner is still working. Taking its claim would produce the second
    store this whole mechanism exists to prevent."""
    session = _Session(rowcount=0)

    assert await service._take_over_stale_claim(session, "ws-1") is False


async def test_only_one_of_two_takers_wins(service):
    """The UPDATE predicate is the lock. The first taker refreshes created_at,
    so the second no longer matches."""
    winner = _Session(rowcount=1)
    loser = _Session(rowcount=0)

    assert await service._take_over_stale_claim(winner, "ws-1") is True
    assert await service._take_over_stale_claim(loser, "ws-1") is False


async def test_stale_threshold_exceeds_a_normal_bootstrap():
    """Taking over faster than CreateStore + WriteAuthorizationModel can finish
    would race the live winner and create a duplicate store."""
    assert doc_acl._STORE_CLAIM_STALE_SECONDS > doc_acl._STORE_CLAIM_TIMEOUT_SECONDS


async def test_get_or_create_takes_over_when_the_insert_is_lost(monkeypatch, service):
    """The path that matters: we lose the claim insert, the existing claim is
    stale, so we take it over and create the store rather than polling to
    timeout and returning None."""
    monkeypatch.setattr(
        service, "_read_store_row", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        service, "_take_over_stale_claim", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(service, "_create_store", AsyncMock(return_value="store-1"))
    monkeypatch.setattr(
        service, "_create_authorization_model", AsyncMock(return_value="model-1")
    )
    awaited = AsyncMock(return_value=None)
    monkeypatch.setattr(service, "_await_store_row", awaited)

    # Insert loses (rowcount 0), takeover wins.
    monkeypatch.setattr(service, "_session_factory", lambda: _Session(rowcount=0))

    result = await service._get_or_create_store("ws-1")

    assert result == ("store-1", "model-1")
    awaited.assert_not_awaited()
