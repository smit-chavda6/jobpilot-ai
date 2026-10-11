"""Cross-tenant authorization sweep test asserting data isolation between users."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_cross_tenant_isolation_sweep(client: AsyncClient):
    # Register User A (Alice)
    res_a = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "alice@tenant-a.com",
            "password": "PasswordAlice123!",
            "full_name": "Alice Tenant",
        },
    )
    token_a = res_a.json()["access_token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # Register User B (Bob)
    res_b = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "bob@tenant-b.com",
            "password": "PasswordBob123!",
            "full_name": "Bob Tenant",
        },
    )
    token_b = res_b.json()["access_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # User A creates a private ProfileFact
    fact_res = await client.post(
        "/api/v1/facts",
        headers=headers_a,
        json={
            "text": "Alice secret internal engineering project experience",
            "category": "project",
            "source_type": "manual",
        },
    )
    assert fact_res.status_code == 201
    fact_id = fact_res.json()["id"]

    # --- Authorization Isolation Assertions ---

    # 1. User B listing facts must NOT see Alice's fact
    bob_facts = await client.get("/api/v1/facts", headers=headers_b)
    assert bob_facts.status_code == 200
    assert len(bob_facts.json()) == 0
    assert not any(f["id"] == fact_id for f in bob_facts.json())

    # 2. User B attempting to confirm Alice's fact must receive 404 Not Found (no cross-tenant leakage)
    bob_confirm = await client.post(f"/api/v1/facts/{fact_id}/confirm", headers=headers_b)
    assert bob_confirm.status_code in [403, 404]

    # 3. User B attempting to reject Alice's fact must receive 404 Not Found
    bob_reject = await client.post(f"/api/v1/facts/{fact_id}/reject", headers=headers_b)
    assert bob_reject.status_code in [403, 404]

    # 4. User B attempting to modify Alice's fact must receive 404 Not Found
    bob_patch = await client.patch(
        f"/api/v1/facts/{fact_id}",
        headers=headers_b,
        json={"text": "Tampered by Bob"},
    )
    assert bob_patch.status_code in [403, 404]

    # 5. User B attempting to delete Alice's fact must receive 404 Not Found
    bob_del = await client.delete(f"/api/v1/facts/{fact_id}", headers=headers_b)
    assert bob_del.status_code in [403, 404]

    # 6. Verify Alice's fact remains intact and untampered
    alice_facts = await client.get("/api/v1/facts", headers=headers_a)
    assert len(alice_facts.json()) == 1
    assert alice_facts.json()[0]["id"] == fact_id
    assert alice_facts.json()[0]["text"] == "Alice secret internal engineering project experience"
