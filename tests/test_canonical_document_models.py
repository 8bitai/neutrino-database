"""[NEU-1816] CANON-DOC-1 — Pydantic models for CanonicalDocument, ViewerSet, Principal.

Pins the shared-package contract for the typed shapes that every
connector + the ingestion pipeline + agent-platform retrieval consume.
These are the Python-side representation of the schema landed by the
Alembic migration c9e0a1b2d3f4 (see test_canonical_document_schema.py).

The shape mirrors `product-feature-roadmap/enterprise-search/
unified-doc-parse-chunk.md`:

  * SourceType — closed enum, 12 kinds
  * PrincipalKind — closed enum, 4 kinds (user, group, workspace_public,
    tenant_public)
  * Principal — provider-native external_id + email + display_name
  * ViewerSet — list[Principal] + is_public_in_workspace + extracted_at
    + extractor_version + unmapped_external_ids
  * CanonicalDocument — the universal document shape

Why these live in the shared package: connector-service builds them,
ES-Ingestion consumes them, agent-platform reads viewers off them. All
three repos depend on neutrino-database, so the types are imported
from one place. Drift between repos is impossible by construction.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError


def test_source_type_enum_has_canonical_values():
    from neutrino_database.models.canonical import SourceType

    expected = {
        "file", "issue", "pull_request", "commit",
        "page", "record", "message", "email",
        "event", "comment", "attachment", "ticket",
    }
    assert {st.value for st in SourceType} == expected, (
        "SourceType must contain exactly the 12 canonical kinds from "
        "unified-doc-parse-chunk.md (Source_type — closed vocabulary)."
    )


def test_principal_kind_enum_is_the_four_canonical_kinds():
    from neutrino_database.models.canonical import PrincipalKind

    expected = {"user", "group", "workspace_public", "tenant_public"}
    assert {k.value for k in PrincipalKind} == expected, (
        "PrincipalKind generalizes provider-specific kinds "
        "(SharePoint user/group/sharepoint_group, Jira user/group/role) "
        "into 4 canonical kinds. See unified-doc-parse-chunk.md § "
        "'Generalization tasks'."
    )


def test_principal_validates_user_kind_requires_email_for_mapping():
    """user-kind principals need email to be mappable to Neutrino
    member.id via user_mapping_service. The shape allows email=None
    (so unmapped principals can still round-trip), but the resolver
    enforces it; v1 ships with the shape permitting None and the
    runtime check in stage 6.5."""
    from neutrino_database.models.canonical import Principal, PrincipalKind

    p = Principal(
        kind=PrincipalKind.USER,
        external_id="62abc:def",
        email="anmol@8bit.ai",
        display_name="Anmol Gautam",
    )
    assert p.kind == PrincipalKind.USER
    assert p.email == "anmol@8bit.ai"

    # user-kind WITHOUT email is allowed at the shape level (resolver
    # writes it to unmapped_external_ids; doc still indexes).
    p2 = Principal(
        kind=PrincipalKind.USER,
        external_id="62abc:no-email",
        email=None,
        display_name=None,
    )
    assert p2.email is None


def test_principal_workspace_public_has_no_external_user_identity():
    """workspace_public is a marker principal — no external_id needed
    for a real user; we use the workspace_id itself."""
    from neutrino_database.models.canonical import Principal, PrincipalKind

    p = Principal(
        kind=PrincipalKind.WORKSPACE_PUBLIC,
        external_id="ws-uuid-here",  # the workspace_id
        email=None,
        display_name=None,
    )
    assert p.kind == PrincipalKind.WORKSPACE_PUBLIC


def test_viewerset_round_trips_through_json():
    """ViewerSet is serialized to JSONB in the files.viewers column.
    Pydantic JSON round-trip must preserve every field — drift here is
    the most-common class of ACL bug in this kind of system."""
    from neutrino_database.models.canonical import (
        Principal, PrincipalKind, ViewerSet,
    )

    vs = ViewerSet(
        principals=[
            Principal(
                kind=PrincipalKind.USER, external_id="62a:1",
                email="a@x.com", display_name="A",
            ),
            Principal(
                kind=PrincipalKind.GROUP, external_id="jira-eng",
                email=None, display_name="Engineering",
            ),
        ],
        is_public_in_workspace=False,
        extracted_at=datetime(2026, 6, 4, 12, 0, 0, tzinfo=timezone.utc),
        extractor_version=1,
        unmapped_external_ids=["62a:unmapped-1"],
    )
    blob = vs.model_dump_json()
    reborn = ViewerSet.model_validate_json(blob)
    assert reborn == vs
    # Confirm the JSONB-shaped dict matches the in-memory shape exactly.
    as_dict = vs.model_dump(mode="json")
    assert as_dict["is_public_in_workspace"] is False
    assert len(as_dict["principals"]) == 2
    assert as_dict["unmapped_external_ids"] == ["62a:unmapped-1"]


def test_viewerset_default_is_default_deny():
    """A freshly-constructed ViewerSet with no principals + no public
    marker means "no one can see this doc" — the safe default-deny
    posture. This is the in-memory equivalent of the column's
    server_default='{}' invariant in the schema test."""
    from neutrino_database.models.canonical import ViewerSet

    vs = ViewerSet(
        principals=[],
        is_public_in_workspace=False,
        extracted_at=datetime(2026, 6, 4, tzinfo=timezone.utc),
        extractor_version=1,
        unmapped_external_ids=[],
    )
    assert vs.principals == []
    assert vs.is_public_in_workspace is False
    # The invariant is enforced by the retrieval filter, not the type —
    # but the shape must support representing "no viewers".


def test_canonical_document_required_fields_are_what_the_doc_says():
    """Pins the must-be-present fields from
    unified-doc-parse-chunk.md's CanonicalDocument class. Missing any
    of these breaks the contract every connector relies on."""
    from neutrino_database.models.canonical import (
        CanonicalDocument, Principal, PrincipalKind, SourceType, ViewerSet,
    )

    doc = CanonicalDocument(
        doc_id=uuid4(),
        external_id="NEU-1816",
        integration_id=uuid4(),
        tenant_id=uuid4(),
        workspace_id=uuid4(),
        provider="jira",
        source_type=SourceType.ISSUE,
        source_url="https://contoso.atlassian.net/browse/NEU-1816",
        title="NEU-1816 Fix tenant owner race",
        title_fallback="X1 shipped — atomic owner-set via UPDATE…",
        container_id="NEU",
        container_name="Neutrino",
        breadcrumb=["Neutrino project"],
        body="The tenant owner race is fixed via an atomic UPDATE...",
        body_format="markdown",
        language="en",
        author_name="Anmol",
        author_email="anmol@8bit.ai",
        created_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
        last_modified=datetime(2026, 6, 4, tzinfo=timezone.utc),
        parent_doc_id=None,
        viewers=ViewerSet(
            principals=[
                Principal(
                    kind=PrincipalKind.USER, external_id="62a:1",
                    email="anmol@8bit.ai", display_name="Anmol",
                ),
            ],
            is_public_in_workspace=False,
            extracted_at=datetime(2026, 6, 4, tzinfo=timezone.utc),
            extractor_version=1,
            unmapped_external_ids=[],
        ),
        facets={"status": "in_progress", "priority": "high"},
        metadata={"epic": "NEU-1816", "fix_versions": ["1.0"]},
    )
    assert doc.provider == "jira"
    assert doc.source_type == SourceType.ISSUE
    assert doc.viewers.principals[0].email == "anmol@8bit.ai"
    # facets vs metadata stay separate (filter-keyword vs display-only).
    assert doc.facets["status"] == "in_progress"
    assert doc.metadata["epic"] == "NEU-1816"


def test_canonical_document_title_nullable_for_messages_and_commits():
    """title is nullable: Slack messages, GitHub commits, email
    snippets have no canonical title. The pipeline falls back to
    title_fallback (body excerpt) for citation rendering."""
    from neutrino_database.models.canonical import (
        CanonicalDocument, PrincipalKind, SourceType, ViewerSet,
    )

    doc = CanonicalDocument(
        doc_id=uuid4(),
        external_id="C01ENG:1717250580.000100",
        integration_id=uuid4(),
        tenant_id=uuid4(),
        workspace_id=uuid4(),
        provider="slack",
        source_type=SourceType.MESSAGE,
        source_url="https://slack.example.com/...",
        title=None,                  # ← messages have none
        title_fallback="Hit a weird race in tenant onboarding…",
        container_id="C01ENG",
        container_name="#engineering",
        breadcrumb=["Contoso", "#engineering"],
        body="Hit a weird race in tenant onboarding…",
        body_format="markdown",
        language="en",
        author_name="Anmol",
        author_email=None,
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        last_modified=datetime(2026, 6, 1, tzinfo=timezone.utc),
        parent_doc_id=None,
        viewers=ViewerSet(
            principals=[], is_public_in_workspace=True,
            extracted_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
            extractor_version=1, unmapped_external_ids=[],
        ),
        facets={"channel": "#engineering"},
        metadata={},
    )
    assert doc.title is None
    assert doc.title_fallback


def test_canonical_document_rejects_unknown_source_type():
    """source_type is a closed vocabulary — anything outside the 12
    kinds is a contract violation, caught at model construction."""
    from neutrino_database.models.canonical import (
        CanonicalDocument, PrincipalKind, ViewerSet,
    )

    with pytest.raises(ValidationError):
        CanonicalDocument(
            doc_id=uuid4(),
            external_id="x",
            integration_id=uuid4(),
            tenant_id=uuid4(),
            workspace_id=uuid4(),
            provider="custom",
            source_type="cuneiform-tablet",  # ← not in SourceType
            source_url="https://x",
            title="x", title_fallback="x",
            container_id="x", container_name="x", breadcrumb=[],
            body="x", body_format="markdown", language=None,
            author_name=None, author_email=None,
            created_at=datetime.now(timezone.utc),
            last_modified=datetime.now(timezone.utc),
            parent_doc_id=None,
            viewers=ViewerSet(
                principals=[], is_public_in_workspace=False,
                extracted_at=datetime.now(timezone.utc),
                extractor_version=1, unmapped_external_ids=[],
            ),
            facets={}, metadata={},
        )


def test_canonical_document_doc_id_is_deterministic_helper():
    """uuid5 helper produces the same UUID for the same (tenant,
    provider, external_id) tuple. Re-syncs upsert; never duplicate."""
    from neutrino_database.models.canonical import build_doc_id

    tenant = uuid4()
    a = build_doc_id(tenant, "jira", "NEU-1816")
    b = build_doc_id(tenant, "jira", "NEU-1816")
    c = build_doc_id(tenant, "jira", "NEU-1817")
    assert a == b
    assert a != c
    # Same external_id but different provider → different doc_id.
    d = build_doc_id(tenant, "linear", "NEU-1816")
    assert a != d
