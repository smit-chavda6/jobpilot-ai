"""Tests for candidate profile management."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_profile_lifecycle(client: AsyncClient):
    # 1. Register candidate
    reg = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "profile@example.com",
            "password": "Password123!",
            "full_name": "Profile Candidate",
        },
    )
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Get initial profile
    res = await client.get("/api/v1/profile", headers=headers)
    assert res.status_code == 200
    profile = res.json()
    assert profile["full_name"] == "Profile Candidate"

    # 3. Update profile
    update_res = await client.put(
        "/api/v1/profile",
        headers=headers,
        json={
            "headline": "Lead AI & Backend Engineer",
            "location": "San Francisco, CA",
            "remote_preference": "remote",
            "target_roles": ["Staff Engineer", "Lead AI Engineer"],
            "min_salary": 180000,
        },
    )
    assert update_res.status_code == 200
    updated = update_res.json()
    assert updated["headline"] == "Lead AI & Backend Engineer"
    assert updated["min_salary"] == 180000

    # 4. Add Education
    edu_res = await client.post(
        "/api/v1/profile/education",
        headers=headers,
        json={
            "institution": "University of California, Berkeley",
            "degree": "B.S. Computer Science",
            "start_date": "2018",
            "end_date": "2022",
        },
    )
    assert edu_res.status_code == 201
    assert edu_res.json()["institution"] == "University of California, Berkeley"

    # 5. Add Experience
    exp_res = await client.post(
        "/api/v1/profile/experience",
        headers=headers,
        json={
            "company": "Tech Corp",
            "title": "Senior Software Engineer",
            "location": "San Francisco, CA",
            "is_current": True,
            "description": "Architected distributed async workflow engine in Python & FastAPI",
        },
    )
    assert exp_res.status_code == 201
    assert exp_res.json()["company"] == "Tech Corp"

    # 6. Verify full profile reflects nested records
    final_res = await client.get("/api/v1/profile", headers=headers)
    final_profile = final_res.json()
    assert len(final_profile["educations"]) == 1
    assert len(final_profile["experiences"]) == 1
