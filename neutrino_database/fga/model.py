"""Canonical OpenFGA authorization model — load + semantic hash (NC-113-a).

The model JSON (``model.json``, in this package) is the single source of truth
both connector-service and ES-Ingestion load. ``model_hash`` produces a
``SEMANTIC`` fingerprint of a model so the migrator can ask "is the model
deployed on this store the same schema as the source?" — a model read back
from OpenFGA carries an assigned ``id``, may reorder keys, normalize empty
``metadata``/``relations``, drop the empty ``object: ""`` on a computedUserset,
and add server-only fields. None of those are schema changes, so the hash
projects each model down to its meaning — types → relation rewrites + the
directly-related user-types — and ignores the serialization noise.
"""

from __future__ import annotations

import hashlib
import json
import re
from functools import lru_cache
from importlib import resources
from typing import Any

_CAMEL_RE = re.compile(r"(?<!^)(?=[A-Z])")


def _snake(key: str) -> str:
    """``computedUserset`` -> ``computed_userset``. OpenFGA's JSON wire format
    (our source) is camelCase; the openfga_sdk ``.to_dict()`` read-back is
    snake_case. Normalize both sides to snake_case before hashing."""
    return _CAMEL_RE.sub("_", key).lower()

# Bump when the model.json schema changes. Advisory/human-facing; the migrator
# decides drift from the semantic hash, not this string.
MODEL_VERSION = "1.1.0"


@lru_cache(maxsize=1)
def load_model() -> dict[str, Any]:
    """Return the canonical authorization model as a dict.

    Loaded via ``importlib.resources`` so it works the same whether the package
    is installed editable (dev) or as a wheel (prod).
    """
    raw = resources.files("neutrino_database.fga").joinpath("model.json").read_text()
    return json.loads(raw)


def _norm_rewrite(node: Any) -> Any:
    """Canonicalize a relation rewrite (userset) so our source model and the
    same model read back from OpenFGA's SDK fingerprint identically.

    The SDK ``.to_dict()`` read-back differs from our source JSON in three
    benign ways, all normalized here:
      * snake_case keys (``computed_userset``) vs our camelCase (``computedUserset``);
      * every inactive userset field materialized as ``null`` (``this: null``,
        ``union: null`` …) — dropped;
      * the optional empty ``object: ""`` on a computedUserset — dropped
        ("this object" either way).
    Key order is handled by ``sort_keys`` at dump time.
    """
    if isinstance(node, dict):
        out: dict[str, Any] = {}
        for k, v in node.items():
            if v is None:
                continue  # SDK materializes inactive userset fields as null
            if k == "object" and v == "":
                continue  # benign "this object"
            out[_snake(k)] = _norm_rewrite(v)
        return out
    if isinstance(node, list):
        return [_norm_rewrite(v) for v in node]
    return node


def _principals(dr_list: Any) -> list[tuple[Any, Any, bool]]:
    """Normalize ``directly_related_user_types`` to a sorted, comparable set of
    ``(type, relation, is_wildcard)`` — order-insensitive."""
    return sorted(
        (d.get("type"), d.get("relation"), d.get("wildcard") is not None)
        for d in (dr_list or [])
    )


def _semantic(model: dict[str, Any]) -> dict[str, Any]:
    """Project a model down to its schema meaning, discarding ``id``, empty
    ``metadata``/``relations``, key order, and server-only fields."""
    types: dict[str, Any] = {}
    for t in model.get("type_definitions", []):
        relations = t.get("relations") or {}
        meta_rel = ((t.get("metadata") or {}).get("relations")) or {}
        types[t["type"]] = {
            "relations": {name: _norm_rewrite(rw) for name, rw in relations.items()},
            "user_types": {
                name: _principals((meta_rel.get(name) or {}).get("directly_related_user_types"))
                for name in relations
            },
        }
    return {"schema_version": model.get("schema_version"), "types": types}


def model_hash(model: dict[str, Any]) -> str:
    """Stable SHA-256 of a model's *meaning* — equal for our source model and
    the same model read back from OpenFGA. The migrator compares the two to
    decide whether a store is already at head.
    """
    canonical = json.dumps(_semantic(model), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# Precomputed fingerprint of the source model — the migrator's "head".
SOURCE_MODEL_HASH = model_hash(load_model())
