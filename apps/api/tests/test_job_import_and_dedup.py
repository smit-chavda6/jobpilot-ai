"""Tests for Job Ingestion, SSRF Protection, and Idempotent Deduplication."""

import io

import pytest
from fastapi import HTTPException
from httpx import AsyncClient

from apps.api.adapters.base import JobDraft
from apps.api.services.job_ingestion_service import JobIngestionService
from apps.api.services.ssrf_protector import is_ip_blocked, validate_url_for_ssrf


def test_ssrf_protection_matrix():
    """Validates that SSRF validator rejects private IPs, loopback, cloud metadata, and forbidden schemes."""
    # 1. Loopback addresses
    with pytest.raises(HTTPException) as exc1:
        validate_url_for_ssrf("http://127.0.0.1:8000/admin")
    assert exc1.value.status_code == 400

    with pytest.raises(HTTPException):
        validate_url_for_ssrf("http://localhost/secrets")

    # 2. Cloud metadata IP (AWS, GCP, Azure instance metadata)
    with pytest.raises(HTTPException) as exc2:
        validate_url_for_ssrf("http://169.254.169.254/latest/meta-data/")
    assert exc2.value.status_code == 400

    # 3. RFC 1918 Private subnets
    assert is_ip_blocked("10.0.0.5") is True
    assert is_ip_blocked("172.16.0.100") is True
    assert is_ip_blocked("192.168.1.1") is True

    # 4. Forbidden schemes (non-http/https)
    with pytest.raises(HTTPException) as exc3:
        validate_url_for_ssrf("file:///etc/passwd")
    assert exc3.value.status_code == 400

    with pytest.raises(HTTPException):
        validate_url_for_ssrf("gopher://internal-service:70")

    # 5. Public IPs are permitted
    assert is_ip_blocked("8.8.8.8") is False
    assert is_ip_blocked("1.1.1.1") is False


@pytest.mark.asyncio
async def test_idempotent_job_deduplication(client: AsyncClient, db_session):
    """Proves that ingesting the identical job listing multiple times creates exactly 1 record."""
    # 1. Register candidate
    reg = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "dedup_tester@example.com",
            "password": "Password123!",
            "full_name": "Dedup Tester",
        },
    )
    user_id = reg.json()["user"]["id"]
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Create JobDraft
    draft = JobDraft(
        title="Staff Site Reliability Engineer",
        company="Stripe",
        description="Lead global infrastructure reliability and incident response.",
        location="San Francisco, CA",
        remote_type="remote",
        employment_type="full-time",
        required_skills=["Python", "Linux", "Kubernetes"],
        source_id="manual",
        source_url="https://stripe.com/jobs/sre-123",
    )

    ingestion_service = JobIngestionService(db_session)

    # First Ingestion
    job1, is_new1 = await ingestion_service.ingest_job_draft(user_id, draft)
    assert is_new1 is True
    assert job1.id is not None
    initial_job_id = job1.id

    # Second Ingestion of identical listing (Idempotent re-import)
    job2, is_new2 = await ingestion_service.ingest_job_draft(user_id, draft)
    assert is_new2 is False
    assert job2.id == initial_job_id

    # Verify query returns exactly 1 job listing
    list_res = await client.get("/api/v1/jobs", headers=headers)
    assert list_res.status_code == 200
    jobs = list_res.json()
    assert len(jobs) == 1
    assert jobs[0]["id"] == initial_job_id


@pytest.mark.asyncio
async def test_structured_file_import_json_and_csv(client: AsyncClient):
    """Validates that uploaded CSV and JSON files are parsed and ingested cleanly."""
    reg = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "file_import_user@example.com",
            "password": "Password123!",
            "full_name": "File Importer",
        },
    )
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. JSON file import
    json_payload = """[
        {
            "title": "Senior Backend Engineer",
            "company": "Datadog",
            "location": "New York, NY",
            "description": "Architect telemetry streaming microservices with Python and FastAPI.",
            "skills": ["Python", "FastAPI", "Redis"]
        }
    ]"""
    json_file = {"file": ("jobs.json", io.BytesIO(json_payload.encode()), "application/json")}
    res_json = await client.post("/api/v1/jobs/import/file", headers=headers, files=json_file)
    assert res_json.status_code == 201
    assert len(res_json.json()) == 1
    assert res_json.json()[0]["company"] == "Datadog"

    # 2. CSV file import
    csv_payload = "title,company,location,description\nStaff Infrastructure Engineer,Figma,Remote,Manage multi-region AWS and Kubernetes clusters."
    csv_file = {"file": ("jobs.csv", io.BytesIO(csv_payload.encode()), "text/csv")}
    res_csv = await client.post("/api/v1/jobs/import/file", headers=headers, files=csv_file)
    assert res_csv.status_code == 201
    assert len(res_csv.json()) == 1
    assert res_csv.json()[0]["company"] == "Figma"

    # 3. Verify total 2 jobs stored
    all_jobs_res = await client.get("/api/v1/jobs", headers=headers)
    assert len(all_jobs_res.json()) == 2
