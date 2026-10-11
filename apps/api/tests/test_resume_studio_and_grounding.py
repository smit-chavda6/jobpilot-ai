"""Unit and integration tests for M6: Grounding Validator, Resume Studio tailoring, Cover Letters, and ATS Exporters."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models.fact import ProfileFact
from apps.api.models.job import Job
from apps.api.models.resume import Resume
from apps.api.models.user import User
from apps.api.services.cover_letter_service import CoverLetterService
from apps.api.services.export_service import ExportService
from apps.api.services.grounding_validator import GroundingValidator
from apps.api.services.resume_tailor_service import ResumeTailorService


@pytest.fixture
async def sample_user_with_facts(db_session: AsyncSession):
    user = User(
        email="grounding_user@example.com",
        hashed_password="test_argon2_hash",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    fact1 = ProfileFact(
        user_id=user.id,
        text="Architected FastAPI microservices handling 500 RPS with 99.9% uptime at Stripe.",
        category="experience",
        confirmation_status="confirmed",
        source_type="resume",
        entities={"company": "Stripe", "skills": ["FastAPI", "Python"], "metrics": ["500 RPS", "99.9%"]},
    )
    fact2 = ProfileFact(
        user_id=user.id,
        text="Optimized PostgreSQL queries, reducing p99 latency by 45%.",
        category="experience",
        confirmation_status="confirmed",
        source_type="resume",
        entities={"skills": ["PostgreSQL"], "metrics": ["45%"]},
    )
    fact3 = ProfileFact(
        user_id=user.id,
        text="Earned B.S. in Computer Science from University of Michigan with 3.8 GPA.",
        category="education",
        confirmation_status="confirmed",
        source_type="resume",
        entities={"degree": "B.S. in Computer Science", "institution": "University of Michigan"},
    )
    fact4 = ProfileFact(
        user_id=user.id,
        text="Python",
        category="skill",
        confirmation_status="confirmed",
        source_type="profile",
        entities={},
    )
    fact5 = ProfileFact(
        user_id=user.id,
        text="FastAPI",
        category="skill",
        confirmation_status="confirmed",
        source_type="profile",
        entities={},
    )
    # An unconfirmed fact that should be rejected by the grounding validator
    unconfirmed_fact = ProfileFact(
        user_id=user.id,
        text="Implemented Kubernetes cluster failover.",
        category="experience",
        confirmation_status="candidate",
        source_type="resume",
        entities={"skills": ["Kubernetes"]},
    )

    db_session.add_all([fact1, fact2, fact3, fact4, fact5, unconfirmed_fact])
    await db_session.flush()

    return user, [fact1, fact2, fact3, fact4, fact5], unconfirmed_fact


@pytest.mark.asyncio
async def test_grounding_validator_blocks_hallucinations_and_unconfirmed_claims(sample_user_with_facts):
    user, confirmed_facts, unconfirmed_fact = sample_user_with_facts
    validator = GroundingValidator(confirmed_facts)

    f1 = confirmed_facts[0]

    # 1. Valid grounded claim citing confirmed fact with exact matching metric
    valid_res = validator.validate_content([
        {
            "text": "Architected FastAPI microservices handling 500 RPS with 99.9% uptime at Stripe.",
            "cited_fact_ids": [f1.id],
        }
    ])
    assert valid_res.is_grounded is True
    assert valid_res.grounding_score == 1.0
    assert len(valid_res.violations) == 0

    # 2. Claim citing unconfirmed candidate fact must be rejected
    unconfirmed_res = validator.validate_content([
        {
            "text": "Implemented Kubernetes cluster failover.",
            "cited_fact_ids": [unconfirmed_fact.id],
        }
    ])
    assert unconfirmed_res.is_grounded is False
    assert any("Unconfirmed or invalid citation" in v for v in unconfirmed_res.violations)

    # 3. Temptation to hallucinate: Invented metric (claimed 10x and 300% improvement)
    hallucinated_metric_res = validator.validate_content([
        {
            "text": "Achieved 10x throughput scaling and 300% performance gain.",
            "cited_fact_ids": [f1.id],
        }
    ])
    assert hallucinated_metric_res.is_grounded is False
    assert any("Invented metric" in v for v in hallucinated_metric_res.violations)

    # 4. Temptation to hallucinate: Unlisted degree (PhD)
    hallucinated_degree_res = validator.validate_content([
        {
            "text": "Completed PhD research in distributed systems.",
            "cited_fact_ids": [f1.id],
        }
    ])
    assert hallucinated_degree_res.is_grounded is False
    assert any("Unlisted degree" in v for v in hallucinated_degree_res.violations)

    # 5. Temptation to hallucinate: Unsupported technology (Kubernetes, Go)
    hallucinated_tech_res = validator.validate_content([
        {
            "text": "Engineered high-concurrency Go microservices running on Kubernetes.",
            "cited_fact_ids": [f1.id],
        }
    ])
    assert hallucinated_tech_res.is_grounded is False
    assert any("Unsupported technology" in v for v in hallucinated_tech_res.violations)


@pytest.mark.asyncio
async def test_synthetic_temptation_to_hallucinate_dataset(sample_user_with_facts):
    """Exit gate assertion: 0 ungrounded claims pass the validator across synthetic temptations."""
    _, confirmed_facts, _ = sample_user_with_facts
    validator = GroundingValidator(confirmed_facts)
    f1 = confirmed_facts[0]

    synthetic_hallucinations = [
        {"text": "Led 15 engineers as VP of Engineering.", "cited_fact_ids": [f1.id]},
        {"text": "Scaled systems to 10000000 active users.", "cited_fact_ids": [f1.id]},
        {"text": "Earned Doctorate degree from MIT.", "cited_fact_ids": [f1.id]},
        {"text": "Deployed enterprise Rust and Golang microservices.", "cited_fact_ids": [f1.id]},
        {"text": "Managed $5,000,000 cloud infrastructure budget.", "cited_fact_ids": [f1.id]},
        {"text": "Boosted conversions by 88%.", "cited_fact_ids": [f1.id]},
        {"text": "Uncited claim with no provenance.", "cited_fact_ids": []},
        {"text": "Claim with fake uuid.", "cited_fact_ids": ["00000000-0000-0000-0000-000000000000"]},
    ]

    for item in synthetic_hallucinations:
        result = validator.validate_content([item])
        # STRICT EXIT GATE: 0 ungrounded claims may pass
        assert result.is_grounded is False, f"Failed: Hallucinated claim '{item['text']}' was not blocked!"


@pytest.mark.asyncio
async def test_tailored_resume_generation_and_diff(sample_user_with_facts, db_session: AsyncSession):
    user, confirmed_facts, _ = sample_user_with_facts

    job = Job(
        user_id=user.id,
        job_fingerprint="fintech-python-lead",
        title="Senior Python Backend Engineer",
        company="Fintech Scaleup",
        location="San Francisco, CA",
        remote_type="remote",
        description="Looking for senior python engineer to scale backend services with FastAPI and PostgreSQL.",
        required_skills=["python", "fastapi"],
        preferred_skills=["postgresql"],
    )
    db_session.add(job)

    resume = Resume(
        user_id=user.id,
        filename="elena_resume.pdf",
        file_path="uploads/mock_elena.pdf",
        file_size=1024,
        mime_type="application/pdf",
        raw_text="Elena Rostova\nPython Developer",
        parsed_data={"skills": ["Python", "FastAPI"], "summary": "Software engineer"},
        is_primary=True,
    )
    db_session.add(resume)
    await db_session.flush()

    tailor_svc = ResumeTailorService()
    result = tailor_svc.tailor_resume(
        resume=resume,
        job=job,
        confirmed_facts=confirmed_facts,
        candidate_name="Elena Rostova",
        candidate_email=user.email,
    )

    assert result["is_valid"] is True
    assert result["grounding_score"] == 1.0
    assert len(result["violations"]) == 0

    # Verify structured diff with provenance annotations
    diff = result["diff"]
    assert "summary_change" in diff
    assert "skill_reordering" in diff
    assert "bullet_adjustments" in diff
    assert len(diff["bullet_adjustments"]) > 0
    assert "fact_id" in diff["bullet_adjustments"][0]
    assert "rationale" in diff["bullet_adjustments"][0]


@pytest.mark.asyncio
async def test_cover_letter_generation_structure(sample_user_with_facts, db_session: AsyncSession):
    user, confirmed_facts, _ = sample_user_with_facts

    job = Job(
        user_id=user.id,
        job_fingerprint="cloudcorp-staff-backend",
        title="Staff Backend Engineer",
        company="CloudCorp",
        location="Remote",
        remote_type="remote",
        description="Looking for staff backend engineer to lead high-throughput microservices.",
        required_skills=["python", "fastapi"],
    )
    db_session.add(job)
    await db_session.flush()

    cover_svc = CoverLetterService()
    letter = cover_svc.generate_grounded_letter(
        candidate_name="Elena Rostova",
        job=job,
        confirmed_facts=confirmed_facts,
    )

    assert letter["is_valid"] is True
    assert len(letter["paragraphs"]) == 3
    assert letter["paragraphs"][0]["section"] == "hook"
    assert letter["paragraphs"][1]["section"] == "evidence"
    assert letter["paragraphs"][2]["section"] == "alignment_close"
    assert len(letter["paragraphs"][1]["cited_fact_ids"]) > 0


@pytest.mark.asyncio
async def test_pdf_and_docx_export_text_roundtrip():
    resume_payload = {
        "header": {
            "name": "Elena Rostova",
            "email": "elena@example.com",
            "target_role": "Senior Backend Engineer",
        },
        "summary": {
            "text": "Experienced distributed systems engineer with verified expertise in FastAPI and PostgreSQL.",
        },
        "skills": [
            {"name": "Python"},
            {"name": "FastAPI"},
            {"name": "PostgreSQL"},
        ],
        "bullets": [
            {"text": "Architected FastAPI microservices handling 500 RPS with 99.9% uptime."},
            {"text": "Optimized PostgreSQL queries, reducing p99 latency by 45%."},
        ],
        "education": [
            {"text": "B.S. in Computer Science - University of Michigan"},
        ],
    }

    # 1. PDF Export
    pdf_bytes = ExportService.generate_pdf(resume_payload)
    assert len(pdf_bytes) > 0
    assert pdf_bytes.startswith(b"%PDF")

    # Round-trip PDF extraction
    pdf_roundtrip_ok = ExportService.validate_pdf_roundtrip(
        pdf_bytes,
        expected_keywords=["Elena Rostova", "FastAPI", "500 RPS", "PostgreSQL", "University of Michigan"],
    )
    assert pdf_roundtrip_ok is True, "PDF text round-trip verification failed!"

    # 2. DOCX Export
    docx_bytes = ExportService.generate_docx(resume_payload)
    assert len(docx_bytes) > 0
    assert docx_bytes.startswith(b"PK\x03\x04")  # Standard ZIP / DOCX magic bytes

    # Round-trip DOCX extraction
    docx_roundtrip_ok = ExportService.validate_docx_roundtrip(
        docx_bytes,
        expected_keywords=["Elena Rostova", "FastAPI", "500 RPS", "PostgreSQL", "University of Michigan"],
    )
    assert docx_roundtrip_ok is True, "DOCX text round-trip verification failed!"
