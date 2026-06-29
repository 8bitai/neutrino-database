"""OpenFGA authorization-model source of truth + migrations (NC-113-a).

``neutrino_database`` is the single home for ALL schema migrations — Postgres
(alembic) and now OpenFGA. The canonical authorization model lives here
(``model.json``); connector-service and ES-Ingestion load it instead of
shipping their own divergent copies, and the migrator (``migrate.py``)
converges existing stores on deploy the way ``alembic upgrade head`` converges
the database.
"""

from neutrino_database.fga.model import (
    MODEL_VERSION,
    SOURCE_MODEL_HASH,
    load_model,
    model_hash,
)

__all__ = [
    "MODEL_VERSION",
    "SOURCE_MODEL_HASH",
    "load_model",
    "model_hash",
]
