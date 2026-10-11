"""Tests for Resume upload, parsing, and candidate ProfileFact verification."""

import io

import pytest
from httpx import AsyncClient

SAMPLE_RESUME_TEXT = """
Jane Doe
Senior Distributed Systems & Backend Engineer
San Francisco, CA | jane.doe@example.com

SUMMARY
Passionate engineer with 6+ years of experience designing high-throughput backend services using Python, FastAPI, and PostgreSQL.

WORK EXPERIENCE
Staff Backend Engineer | Stripe (2022 - Present)
- Architected high-availability payment routing pipeline in Python and FastAPI handling 15,000 requests per second.
- Led migration of legacy datastores to PostgreSQL and Redis cluster, decreasing p99 query latency by 35%.
- Implemented automated CI/CD deployment pipelines on AWS and Docker.

Senior Software Engineer | Datadog (2019 - 2022)
- Built distributed telemetry ingestion pipeline processing 2TB daily log data with Kafka.
- Mentored 4 junior engineers on distributed systems best practices.

EDUCATION
- Bachelor of Science in Computer Science, UC Berkeley, 2019. GPA: 3.8/4.0.

SKILLS
Python, FastAPI, PostgreSQL, Redis, Docker, Kubernetes, AWS, Kafka, Linux, SQL
"""


@pytest.mark.asyncio
async def test_resume_upload_and_parse_lifecycle(client: AsyncClient, db_session):
    # 1. Register candidate
    reg = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "resume_user@example.com",
            "password": "Password123!",
            "full_name": "Jane Doe",
        },
    )
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Upload text resume fixture
    file_bytes = SAMPLE_RESUME_TEXT.encode("utf-8")
    files = {"file": ("resume.txt", io.BytesIO(file_bytes), "text/plain")}

    upload_res = await client.post(
        "/api/v1/resumes/upload",
        headers=headers,
        files=files,
    )
    assert upload_res.status_code == 201
    upload_data = upload_res.json()
    assert upload_data["candidate_facts_count"] > 0
    assert "Python" in upload_data["parsed_skills"]
    assert "FastAPI" in upload_data["parsed_skills"]

    # 3. Verify all generated ProfileFacts have confirmation_status = 'candidate'
    facts_res = await client.get("/api/v1/facts", headers=headers)
    assert facts_res.status_code == 200
    all_facts = facts_res.json()
    assert len(all_facts) == upload_data["candidate_facts_count"]
    assert all(f["confirmation_status"] == "candidate" for f in all_facts)

    # 4. DOWNSTREAM USABILITY INVARIANT:
    # A query for confirmed facts (used by matching & generation) MUST return 0 facts
    confirmed_res = await client.get("/api/v1/facts?status=confirmed", headers=headers)
    assert confirmed_res.status_code == 200
    assert len(confirmed_res.json()) == 0, "Unconfirmed facts must NOT be usable downstream!"

    # 5. User explicitly confirms one fact
    first_fact_id = all_facts[0]["id"]
    confirm_res = await client.post(f"/api/v1/facts/{first_fact_id}/confirm", headers=headers)
    assert confirm_res.status_code == 200
    assert confirm_res.json()["confirmation_status"] == "confirmed"

    # 6. Now exactly 1 fact is usable downstream
    confirmed_after = await client.get("/api/v1/facts?status=confirmed", headers=headers)
    assert len(confirmed_after.json()) == 1
    assert confirmed_after.json()[0]["id"] == first_fact_id


@pytest.mark.asyncio
async def test_invalid_upload_rejected(client: AsyncClient):
    reg = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "invalid_upload@example.com",
            "password": "Password123!",
            "full_name": "Test User",
        },
    )
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Upload arbitrary non-text executable binary content
    fake_exe = b"\x4d\x5a\x90\x00\x03\x00\x00\x00"  # MZ DOS header
    files = {"file": ("malicious.exe", io.BytesIO(fake_exe), "application/octet-stream")}

    res = await client.post(
        "/api/v1/resumes/upload",
        headers=headers,
        files=files,
    )
    # Magic-byte check rejects unsupported binary formats
    assert res.status_code == 415
    assert "Unsupported file format" in res.json()["error"]["message"]
