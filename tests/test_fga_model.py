"""[NC-113-a] FGA model SSOT — the single source of truth for the OpenFGA
authorization model, shared by connector-service and ES-Ingestion.

These two services historically shipped DIVERGENT ``openfga_model.json``
(connector stale: user + doc/can_access; ingestion correct: + group/workspace/
tenant + doc.viewer). Whichever created a store first stamped its model, and
the model is never updated on an existing store — so canonical viewer-tuple
writes 400'd. Centralizing the model here kills the divergence; the migrator
(Phase 2) converges existing stores.

Pins:
  1. The model loads and is the schema OpenFGA expects (schema_version 1.1).
  2. It carries every type + relation the canonical ACL pipeline needs —
     ``user/group/workspace/tenant`` and ``doc.{can_access, viewer}`` with
     ``can_access = this OR viewer``.
  3. ``model_hash`` is a SEMANTIC fingerprint: it's equal for our source model
     and the same model read back from OpenFGA (which adds an ``id``, may
     normalize empty metadata, and may drop the empty ``object: ""`` on a
     computedUserset) — the stateless migrator compares the two to decide
     "already at head" — and it changes when the schema genuinely changes.
"""

from __future__ import annotations

import copy

from neutrino_database.fga import model as fga_model


def test_load_model_is_valid():
    m = fga_model.load_model()
    assert isinstance(m, dict)
    assert m["schema_version"] == "1.1"
    assert isinstance(m["type_definitions"], list) and m["type_definitions"]


def test_model_has_required_types_and_relations():
    m = fga_model.load_model()
    types = {t["type"]: t for t in m["type_definitions"]}

    # Every principal kind the canonical resolver emits must have a type.
    assert {"user", "group", "workspace", "tenant", "doc"} <= set(types)

    doc = types["doc"]
    assert set(doc["relations"]) == {"can_access", "viewer"}
    # can_access must be the union of direct grants OR the viewer relation —
    # this is what lets per-user can_access AND canonical viewer tuples both
    # surface in list_objects(can_access, ...).
    children = doc["relations"]["can_access"]["union"]["child"]
    assert {"this": {}} in children
    assert any(c.get("computedUserset", {}).get("relation") == "viewer"
               for c in children)

    # viewer must accept the four principal user-types.
    viewer_types = {
        (d["type"], d.get("relation"))
        for d in doc["metadata"]["relations"]["viewer"]["directly_related_user_types"]
    }
    assert ("user", None) in viewer_types
    assert ("workspace", "member") in viewer_types
    assert ("tenant", "member") in viewer_types
    assert ("group", "member") in viewer_types


def test_model_hash_is_stable():
    h1 = fga_model.model_hash(fga_model.load_model())
    h2 = fga_model.model_hash(fga_model.load_model())
    assert h1 == h2 == fga_model.SOURCE_MODEL_HASH


# OpenFGA's openfga_sdk ``.to_dict()`` read-back materializes EVERY userset
# field, snake_cased, with ``null`` for the inactive ones. These helpers mirror
# that exact shape so the test guards the real serialization (an earlier,
# unfaithful fixture using camelCase + no nulls let a hash mismatch through to
# the live migrator, which then rewrote the model on every run).
_USERSET_NULL = {
    "computed_userset": None, "difference": None, "intersection": None,
    "this": None, "tuple_to_userset": None, "union": None,
}


def _sdk_this() -> dict:
    return {**_USERSET_NULL, "this": {}}


def _sdk_computed(relation: str) -> dict:
    return {**_USERSET_NULL, "computed_userset": {"relation": relation}}


def _sdk_union(children: list[dict]) -> dict:
    return {**_USERSET_NULL, "union": {"child": children}}


def test_model_hash_matches_a_deployed_readback():
    """The migrator compares the source hash to the hash of the model read back
    from OpenFGA's SDK. Build that faithful read-back — assigned ``id``,
    materialized empty ``metadata``, snake_cased usersets with every inactive
    field as ``null`` — and assert the hash is unchanged (else the migrator
    rewrites the model on every run and idempotency breaks)."""
    src = fga_model.load_model()
    types = {t["type"]: t for t in src["type_definitions"]}

    def _deployed_type(name: str, relations: dict) -> dict:
        t = copy.deepcopy(types[name])
        t["relations"] = relations
        return t

    deployed = {
        "id": "01ABCDEF0123456789",
        "schema_version": src["schema_version"],
        "type_definitions": [
            {"type": "user", "relations": {}, "metadata": {}},
            _deployed_type("group", {"member": _sdk_this()}),
            _deployed_type("workspace", {"member": _sdk_this()}),
            _deployed_type("tenant", {"member": _sdk_this()}),
            _deployed_type("doc", {
                "can_access": _sdk_union([_sdk_this(), _sdk_computed("viewer")]),
                "viewer": _sdk_this(),
            }),
        ],
    }

    assert fga_model.model_hash(deployed) == fga_model.SOURCE_MODEL_HASH


def test_model_hash_changes_on_schema_change():
    drifted = copy.deepcopy(fga_model.load_model())
    drifted["type_definitions"].append({"type": "folder"})
    assert fga_model.model_hash(drifted) != fga_model.SOURCE_MODEL_HASH
