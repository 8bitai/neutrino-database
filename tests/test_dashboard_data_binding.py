"""DashboardWidgetDataBinding — one widget, one query, either language.

A widget is a query re-executed on every dashboard load, and originally that
query could only be SQL. That quietly made dashboards a relational-only
surface: a chart over a Mongo collection could be produced in chat but never
kept, purely because of where its data lived. Nothing about the user's intent
changes between the two, so the binding carries either shape and the executor
is chosen from the shape.

These tests pin the discriminator, because "which executor runs this widget" is
decided entirely by which fields are populated.
"""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from neutrino_database.models.da_schemas import DashboardWidgetDataBinding


def _relational(**over):
    return {
        "connection_id": uuid.uuid4(),
        "schema_name": "sales",
        "sql": "SELECT region, revenue FROM sales.by_region",
        **over,
    }


def _document(**over):
    return {
        "connection_id": uuid.uuid4(),
        "database": "analytics",
        "collection": "customers",
        "pipeline": [{"$group": {"_id": "$tier", "n": {"$sum": 1}}}],
        **over,
    }


class TestBothFormsAreValid:
    def test_relational_binding(self):
        b = DashboardWidgetDataBinding(**_relational())
        assert b.is_document is False
        assert b.sql.startswith("SELECT")

    def test_document_binding(self):
        b = DashboardWidgetDataBinding(**_document())
        assert b.is_document is True
        assert b.collection == "customers"
        assert b.pipeline[0]["$group"]["_id"] == "$tier"

    def test_a_pipeline_survives_verbatim(self):
        """Stored and forwarded opaquely — connector-service's mongo_guard is
        what rejects a write stage, exactly as for a pipeline sent from chat.
        Nothing here may normalise or reshape it."""
        pipeline = [
            {"$match": {"tier": "gold"}},
            {"$group": {"_id": "$region", "n": {"$sum": 1}}},
            {"$sort": {"n": -1}},
            {"$limit": 20},
        ]
        b = DashboardWidgetDataBinding(**_document(pipeline=pipeline))
        assert b.pipeline == pipeline

    def test_an_empty_pipeline_is_still_a_document_binding(self):
        """`pipeline: []` is a real query (every document, no stages) and must
        not be mistaken for "no pipeline" — the discriminator is presence, not
        truthiness."""
        b = DashboardWidgetDataBinding(**_document(pipeline=[]))
        assert b.is_document is True


class TestExactlyOneForm:
    """A binding carrying both queries is a widget whose behaviour depends on
    which branch is checked first. Unconstructible beats deterministic."""

    def test_both_forms_at_once_is_rejected(self):
        with pytest.raises(ValidationError, match="runs one query"):
            DashboardWidgetDataBinding(**_relational(pipeline=[{"$match": {}}]))

    def test_neither_form_is_rejected(self):
        with pytest.raises(ValidationError, match="requires either sql"):
            DashboardWidgetDataBinding(connection_id=uuid.uuid4())

    def test_a_connection_alone_is_not_a_query(self):
        """Guards the specific regression of loosening sql to Optional: before
        the document form existed, sql was required, so this was impossible."""
        with pytest.raises(ValidationError):
            DashboardWidgetDataBinding(
                connection_id=uuid.uuid4(), schema_name="sales"
            )


class TestEachFormIsComplete:
    def test_sql_without_schema_name_is_rejected(self):
        with pytest.raises(ValidationError, match="requires schema_name"):
            DashboardWidgetDataBinding(**_relational(schema_name=None))

    @pytest.mark.parametrize("missing", ["database", "collection"])
    def test_a_pipeline_needs_its_target(self, missing):
        """A pipeline with no collection to run against would reach
        connector-service and fail there, per widget, on every load."""
        with pytest.raises(ValidationError, match="requires database and collection"):
            DashboardWidgetDataBinding(**_document(**{missing: None}))


class TestRoundTrip:
    def test_a_document_binding_survives_the_jsonb_round_trip(self):
        """data_binding is a JSONB column, so the model is reconstructed from
        whatever was dumped. Nothing may be lost in either direction."""
        original = DashboardWidgetDataBinding(**_document())
        restored = DashboardWidgetDataBinding.model_validate(
            original.model_dump(mode="json")
        )
        assert restored.is_document
        assert restored.pipeline == original.pipeline
        assert restored.database == original.database
        assert restored.collection == original.collection

    def test_a_relational_binding_survives_the_round_trip(self):
        original = DashboardWidgetDataBinding(**_relational())
        restored = DashboardWidgetDataBinding.model_validate(
            original.model_dump(mode="json")
        )
        assert restored.is_document is False
        assert restored.sql == original.sql
