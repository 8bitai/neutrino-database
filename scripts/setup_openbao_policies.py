"""
Setup OpenBao ACL policies for per-service scoped access.

Creates three policies and corresponding service tokens:
  - neutrino-gateway-policy: read/write on secret/data/tenants/*/workspaces/*/llm/*
  - agent-platform-policy:   read-only on secret/data/tenants/*/workspaces/*/llm/*
  - connector-service-policy: read/write on secret/data/tenants/*/workspaces/*/connectors/* and tenants/*/logs/*

Usage:
    export OPENBAO_ADDR=https://openbao-dev.8bit.ai
    export OPENBAO_TOKEN=s.zgFffRo2ODREiR8H6iapPKQy
    python scripts/setup_openbao_policies.py
"""

from __future__ import annotations

import asyncio
import os

import httpx

OPENBAO_ADDR = os.environ["OPENBAO_ADDR"]
OPENBAO_TOKEN = os.environ["OPENBAO_TOKEN"]

POLICIES = {
    "neutrino-gateway-policy": '''
path "secret/data/tenants/*/workspaces/*/llm/*" {
  capabilities = ["create", "update", "read", "delete"]
}

path "secret/metadata/tenants/*/workspaces/*/llm/*" {
  capabilities = ["list", "read", "delete"]
}
''',
    "agent-platform-policy": '''
path "secret/data/tenants/*/workspaces/*/llm/*" {
  capabilities = ["read"]
}

path "secret/metadata/tenants/*/workspaces/*/llm/*" {
  capabilities = ["list", "read"]
}
''',
    "connector-service-policy": '''
path "secret/data/tenants/*/workspaces/*/connectors/*" {
  capabilities = ["create", "update", "read", "delete"]
}

path "secret/metadata/tenants/*/workspaces/*/connectors/*" {
  capabilities = ["list", "read", "delete"]
}

path "secret/data/tenants/*/logs/*" {
  capabilities = ["create", "update", "read", "delete"]
}

path "secret/metadata/tenants/*/logs/*" {
  capabilities = ["list", "read", "delete"]
}
''',
}


async def main() -> None:
    print(f"OpenBao: {OPENBAO_ADDR}")
    print()

    async with httpx.AsyncClient(
        headers={"X-Vault-Token": OPENBAO_TOKEN, "Content-Type": "application/json"},
        timeout=10.0,
    ) as client:
        # Verify connectivity
        health = await client.get(f"{OPENBAO_ADDR}/v1/sys/health")
        print(f"Health check: {health.status_code}\n")

        # Create policies
        for name, hcl in POLICIES.items():
            resp = await client.put(
                f"{OPENBAO_ADDR}/v1/sys/policies/acl/{name}",
                json={"policy": hcl},
            )
            resp.raise_for_status()
            print(f"Created policy: {name}")

        print()

        # Create scoped tokens for each service
        for policy_name in POLICIES:
            service_name = policy_name.replace("-policy", "")
            resp = await client.post(
                f"{OPENBAO_ADDR}/v1/auth/token/create",
                json={
                    "policies": [policy_name],
                    "display_name": service_name,
                    "ttl": "768h",  # 32 days
                    "renewable": True,
                },
            )
            resp.raise_for_status()
            token = resp.json()["auth"]["client_token"]
            print(f"Token for {service_name}: {token}")

    print("\nDone. Update each service's .env with its OPENBAO_TOKEN.")


if __name__ == "__main__":
    asyncio.run(main())
