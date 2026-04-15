"""
One-time migration script: move existing encrypted secrets from PostgreSQL to OpenBao KV v2.

Migrates:
  1. LLM API keys (providers table — AES-256-GCM encrypted)
  2. DA connector credentials (credentials table — Fernet encrypted)
  3. Log connector secrets (log_connectors.config JSONB — Fernet encrypted password/api_key fields)

Usage:
    export DATABASE_URL=postgresql+asyncpg://...
    export WORKSPACE_API_KEY_ENCRYPTION_KEY=...
    export ENCRYPTION_KEY=...  (or ENCRYPTION_PASSWORD=...)
    export OPENBAO_ADDR=https://openbao-dev.8bit.ai
    export OPENBAO_TOKEN=s.zgFffRo2ODREiR8H6iapPKQy
    python scripts/migrate_secrets_to_openbao.py
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import sys
from typing import Any

import httpx
from cryptography.fernet import Fernet
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

OPENBAO_ADDR = os.getenv("OPENBAO_ADDR")
OPENBAO_TOKEN = os.getenv("OPENBAO_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
KV_MOUNT = "secret"


# ── Decrypt helpers ────────────────────────────────────────────────────

def _aes_gcm_decrypt(encrypted_b64: str) -> str:
    key_b64 = os.environ["WORKSPACE_API_KEY_ENCRYPTION_KEY"]
    key_bytes = base64.b64decode(key_b64)
    aesgcm = AESGCM(key_bytes)
    encrypted_data = base64.b64decode(encrypted_b64)
    nonce = encrypted_data[:12]
    ciphertext_with_tag = encrypted_data[12:]
    return aesgcm.decrypt(nonce, ciphertext_with_tag, None).decode("utf-8")


def _get_fernet() -> Fernet:
    enc_key = os.environ.get("ENCRYPTION_KEY")
    enc_password = os.environ.get("ENCRYPTION_PASSWORD")
    if enc_key:
        return Fernet(enc_key.encode())
    elif enc_password:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"connector_service_salt",
            iterations=100000,
            backend=default_backend(),
        )
        key = base64.urlsafe_b64encode(kdf.derive(enc_password.encode()))
        return Fernet(key)
    raise RuntimeError("Set ENCRYPTION_KEY or ENCRYPTION_PASSWORD")


def _fernet_decrypt(encrypted_token: str) -> str:
    return _get_fernet().decrypt(encrypted_token.encode()).decode()


# ── OpenBao KV v2 helper ──────────────────────────────────────────────

async def _kv_put(client: httpx.AsyncClient, path: str, data: dict) -> None:
    url = f"{OPENBAO_ADDR}/v1/{KV_MOUNT}/data/{path}"
    resp = await client.post(url, json={"data": data})
    resp.raise_for_status()


# ── Main migration logic ──────────────────────────────────────────────

async def migrate_providers(session: AsyncSession, vault: httpx.AsyncClient) -> int:
    """Migrate providers.encrypted_value -> OpenBao."""
    result = await session.execute(
        text(
            "SELECT id, workspace_id, encrypted_value "
            "FROM providers "
            "WHERE vault_path IS NULL AND encrypted_value IS NOT NULL AND is_deleted = false"
        )
    )
    rows = result.mappings().all()
    count = 0
    for row in rows:
        pid = str(row["id"])
        wid = str(row["workspace_id"])
        try:
            api_key = _aes_gcm_decrypt(row["encrypted_value"])
        except Exception as exc:
            print(f"  SKIP provider {pid}: decrypt failed: {exc}")
            continue

        vp = f"workspaces/{wid}/llm/{pid}"
        await _kv_put(vault, vp, {"api_key": api_key})

        await session.execute(
            text(
                "UPDATE providers "
                "SET vault_path = :vp, encrypted_value = NULL, encryption_method = 'openbao' "
                "WHERE id = :pid"
            ),
            {"vp": vp, "pid": pid},
        )
        count += 1
        print(f"  Migrated provider {pid} -> {vp}")

    await session.commit()
    return count


async def migrate_credentials(session: AsyncSession, vault: httpx.AsyncClient) -> int:
    """Migrate credentials.access_token_encrypted -> OpenBao (DA creds only)."""
    result = await session.execute(
        text(
            "SELECT cr.id, cr.connection_id, cr.access_token_encrypted, cr.resource, "
            "       co.workspace_id, co.connection_name "
            "FROM credentials cr "
            "JOIN connections co ON co.id = cr.connection_id "
            "WHERE cr.vault_path IS NULL "
            "  AND cr.access_token_encrypted IS NOT NULL "
            "  AND cr.resource = 'da'"
        )
    )
    rows = result.mappings().all()
    count = 0
    for row in rows:
        cid = str(row["id"])
        wid = str(row["workspace_id"])
        cname = str(row["connection_name"])
        try:
            plaintext = _fernet_decrypt(row["access_token_encrypted"])
            creds = json.loads(plaintext)
        except Exception as exc:
            print(f"  SKIP credential {cid}: decrypt failed: {exc}")
            continue

        vp = f"workspaces/{wid}/connectors/{cname}/credentials"
        await _kv_put(vault, vp, creds)

        await session.execute(
            text(
                "UPDATE credentials "
                "SET vault_path = :vp, access_token_encrypted = NULL "
                "WHERE id = :cid"
            ),
            {"vp": vp, "cid": cid},
        )
        count += 1
        print(f"  Migrated credential {cid} -> {vp}")

    await session.commit()
    return count


async def migrate_log_connectors(session: AsyncSession, vault: httpx.AsyncClient) -> int:
    """Migrate encrypted password/api_key from log_connectors.config JSONB -> OpenBao."""
    result = await session.execute(
        text(
            "SELECT id, tenant_id, config "
            "FROM log_connectors "
            "WHERE status = 'active' "
            "  AND config IS NOT NULL "
            "  AND (config->>'_vault_path') IS NULL"
        )
    )
    rows = result.mappings().all()
    count = 0
    for row in rows:
        lcid = str(row["id"])
        tid = str(row["tenant_id"])
        cfg: dict = row["config"] or {}

        secrets: dict[str, str] = {}
        if cfg.get("password"):
            try:
                secrets["password"] = _fernet_decrypt(cfg["password"])
            except Exception:
                pass
        if cfg.get("api_key"):
            try:
                secrets["api_key"] = _fernet_decrypt(cfg["api_key"])
            except Exception:
                pass

        if not secrets:
            continue

        vp = f"workspaces/{tid}/logs/{lcid}"
        await _kv_put(vault, vp, secrets)

        new_cfg = dict(cfg)
        new_cfg.pop("password", None)
        new_cfg.pop("api_key", None)
        new_cfg["_vault_path"] = vp

        await session.execute(
            text("UPDATE log_connectors SET config = :cfg WHERE id = :lcid"),
            {"cfg": json.dumps(new_cfg), "lcid": lcid},
        )
        count += 1
        print(f"  Migrated log_connector {lcid} -> {vp}")

    await session.commit()
    return count


async def main() -> None:
    print("=== OpenBao secret migration ===")
    print(f"Database: {DATABASE_URL.split('@')[-1]}")
    print(f"OpenBao:  {OPENBAO_ADDR}")
    print()

    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with httpx.AsyncClient(
        headers={"X-Vault-Token": OPENBAO_TOKEN, "Content-Type": "application/json"},
        timeout=10.0,
    ) as vault:
        # Verify OpenBao connectivity
        health = await vault.get(f"{OPENBAO_ADDR}/v1/sys/health")
        print(f"OpenBao health: {health.status_code}")
        print()

        async with async_session() as session:
            print("[1/3] Migrating LLM providers ...")
            n1 = await migrate_providers(session, vault)
            print(f"  -> {n1} provider(s) migrated\n")

            print("[2/3] Migrating DA credentials ...")
            n2 = await migrate_credentials(session, vault)
            print(f"  -> {n2} credential(s) migrated\n")

            print("[3/3] Migrating log connector secrets ...")
            n3 = await migrate_log_connectors(session, vault)
            print(f"  -> {n3} log connector(s) migrated\n")

    await engine.dispose()
    print(f"Done. Total: {n1 + n2 + n3} secret(s) migrated to OpenBao.")


if __name__ == "__main__":
    asyncio.run(main())
