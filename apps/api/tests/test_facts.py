"""Tests for atomic verifiable ProfileFacts."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_facts_lifecycle(client: AsyncClient):
    reg = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "facts@example.com",
            "password": "Password123!",
            "full_name": "Fact Candidate",
        },
    )
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Create a candidate fact (e.g. parsed from resume)
    c_res = await client.post(
        "/api/v1/facts",
        headers=headers,
        json={
            "text": "Built high-throughput data processing pipeline with FastAPI and Celery",
            "category": "experience",
            "source_type": "resume",
            "entities": {"skills": ["FastAPI", "Celery", "Python"]},
        },
    )
    assert c_res.status_code == 201
    fact = c_res.json()
    assert fact["confirmation_status"] == "candidate"
    fact_id = fact["id"]

    # 2. Filter by candidate status
    candidates_res = await client.get("/api/v1/facts?status=candidate", headers=headers)
    assert candidates_res.status_code == 200
    assert len(candidates_res.json()) == 1

    # 3. Confirm the fact
    confirm_res = await client.post(f"/api/v1/facts/{fact_id}/confirm", headers=headers)
    assert confirm_res.status_code == 200
    assert confirm_res.json()["confirmation_status"] == "confirmed"

    # 4. Check candidates filter is now empty and confirmed has 1
    cand_after = await client.get("/api/v1/facts?status=candidate", headers=headers)
    assert len(cand_after.json()) == 0

    conf_after = await client.get("/api/v1/facts?status=confirmed", headers=headers)
    assert len(conf_after.json()) == 1

    # 5. Reject fact
    rej_res = await client.post(f"/api/v1/facts/{fact_id}/reject", headers=headers)
    assert rej_res.status_code == 200
    assert rej_res.json()["confirmation_status"] == "rejected"

    # 6. Delete fact
    del_res = await client.delete(f"/api/v1/facts/{fact_id}", headers=headers)
    assert del_res.status_code == 204

    # 7. Verify fact is gone
    final_list = await client.get("/api/v1/facts", headers=headers)
    assert len(final_list.json()) == 0
