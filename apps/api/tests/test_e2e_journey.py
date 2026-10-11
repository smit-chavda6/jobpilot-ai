"""Complete End-to-End integration test covering the entire candidate journey."""

import io
import pytest
from httpx import AsyncClient

from apps.api.services.export_service import ExportService


@pytest.mark.asyncio
async def test_full_candidate_lifecycle_e2e(client: AsyncClient):
    # Step 1: Candidate Registration & Login
    reg_resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "e2e_candidate@jobpilot.ai",
            "password": "SecurePassword123!",
            "full_name": "Elena Rostova",
        },
    )
    assert reg_resp.status_code == 201
    token = reg_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Step 2: Upload Resume (text format fixture)
    resume_content = (
        b"Elena Rostova\n"
        b"Full-Stack Engineer\n\n"
        b"EXPERIENCE\n"
        b"- Architected FastAPI microservices handling 500 RPS with 99.9% uptime at Stripe.\n"
        b"- Optimized PostgreSQL queries, reducing p99 latency by 45%.\n\n"
        b"EDUCATION\n"
        b"- B.S. in Computer Science - University of Michigan\n\n"
        b"SKILLS\n"
        b"Python, FastAPI, PostgreSQL, React, TypeScript\n"
    )
    upload_resp = await client.post(
        "/api/v1/resumes/upload",
        headers=headers,
        files={"file": ("elena_resume.txt", io.BytesIO(resume_content), "text/plain")},
    )
    assert upload_resp.status_code == 201
    upload_data = upload_resp.json()
    resume_id = upload_data["resume_id"]
    assert upload_data["candidate_facts_count"] > 0

    # Step 3: Fetch candidate facts & Confirm them (Truth over Polish)
    facts_resp = await client.get("/api/v1/facts?confirmation_status=candidate", headers=headers)
    assert facts_resp.status_code == 200
    candidate_facts = facts_resp.json()
    assert len(candidate_facts) > 0

    # Confirm all generated facts
    for f in candidate_facts:
        conf_resp = await client.post(f"/api/v1/facts/{f['id']}/confirm", headers=headers)
        assert conf_resp.status_code == 200

    # Step 4: Ingest Target Job via structured JSON payload file
    import json
    jobs_json = json.dumps([{
        "title": "Senior Backend Engineer",
        "company": "Stripe",
        "location": "Remote",
        "remote_type": "remote",
        "description": "Scale core financial APIs using Python and PostgreSQL.",
        "salary_min": 180000,
        "salary_max": 230000,
        "required_skills": ["python", "fastapi"],
        "preferred_skills": ["postgresql"],
    }]).encode("utf-8")
    job_import_resp = await client.post(
        "/api/v1/jobs/import/file",
        headers=headers,
        files={"file": ("jobs.json", io.BytesIO(jobs_json), "application/json")},
    )
    assert job_import_resp.status_code == 201
    imported_jobs = job_import_resp.json()
    assert len(imported_jobs) == 1
    target_job_id = imported_jobs[0]["id"]

    # Step 5: Match Engine Evaluation with Explanations
    match_resp = await client.post(
        f"/api/v1/jobs/{target_job_id}/match",
        headers=headers,
    )
    assert match_resp.status_code == 200
    match_data = match_resp.json()
    assert match_data["score"] >= 75.0
    assert match_data["confidence"] >= 0.70
    assert "fit_reasons" in match_data["explanation"]
    assert "matched_skills" in match_data["explanation"]

    # Step 6: Tailor Resume with Structured Diff View
    tailor_resp = await client.post(
        f"/api/v1/resumes/{resume_id}/tailor",
        headers=headers,
        json={"target_job_id": target_job_id},
    )
    assert tailor_resp.status_code == 201
    tailor_data = tailor_resp.json()
    version_id = tailor_data["version_id"]
    assert tailor_data["is_grounded"] is True
    assert "summary_change" in tailor_data["diff"]
    assert "skill_reordering" in tailor_data["diff"]

    # Step 7: Create Tracked Application & Progress through State Machine
    app_create_resp = await client.post(
        "/api/v1/applications",
        headers=headers,
        json={"job_id": target_job_id, "notes": "E2E application test"},
    )
    assert app_create_resp.status_code == 201
    app_id = app_create_resp.json()["id"]

    # Legal progression: saved -> preparing -> ready_for_review
    t1 = await client.post(
        f"/api/v1/applications/{app_id}/transition",
        headers=headers,
        json={"target_status": "preparing"},
    )
    assert t1.status_code == 200

    # Attach tailored materials
    patch_resp = await client.patch(
        f"/api/v1/applications/{app_id}",
        headers=headers,
        json={
            "resume_version_id": version_id,
            "cover_letter": "Tailored cover letter grounded in verified facts.",
        },
    )
    assert patch_resp.status_code == 200

    t2 = await client.post(
        f"/api/v1/applications/{app_id}/transition",
        headers=headers,
        json={"target_status": "ready_for_review"},
    )
    assert t2.status_code == 200

    # Cryptographically Approve submission package (SHA-256)
    approve_resp = await client.post(
        f"/api/v1/applications/{app_id}/approve",
        headers=headers,
        json={"confirmed_by_user": True},
    )
    assert approve_resp.status_code == 200
    approval_hash = approve_resp.json()["payload_hash"]
    assert len(approval_hash) == 64

    # Transition approved -> submitting -> submitted_confirmed (Human Confirmation Gate)
    t3 = await client.post(
        f"/api/v1/applications/{app_id}/transition",
        headers=headers,
        json={"target_status": "submitting"},
    )
    assert t3.status_code == 200

    t4 = await client.post(
        f"/api/v1/applications/{app_id}/transition",
        headers=headers,
        json={"target_status": "submitted_confirmed", "confirmed_by_user": True},
    )
    assert t4.status_code == 200
    assert t4.json()["status"] == "submitted_confirmed"

    # Step 8: ATS Clean Export (PDF and DOCX) Round-Trip Validation
    pdf_export = await client.get(
        f"/api/v1/resumes/versions/{version_id}/export/pdf",
        headers=headers,
    )
    assert pdf_export.status_code == 200
    assert pdf_export.headers["content-type"] == "application/pdf"
    assert ExportService.validate_pdf_roundtrip(
        pdf_export.content,
        expected_keywords=["FastAPI", "Stripe"],
    )

    docx_export = await client.get(
        f"/api/v1/resumes/versions/{version_id}/export/docx",
        headers=headers,
    )
    assert docx_export.status_code == 200
    assert ExportService.validate_docx_roundtrip(
        docx_export.content,
        expected_keywords=["FastAPI", "Stripe"],
    )
