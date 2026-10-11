"""Unit tests, property tests, and eval harness verification for Matching Engine."""

import pytest
from httpx import AsyncClient

from apps.api.models.fact import ProfileFact
from apps.api.models.job import Job
from apps.api.services.matching_service import MatchingService
from evals.matching.runner import evaluate_matching_engine


@pytest.mark.asyncio
async def test_matching_engine_hard_filters_and_unknowns(client: AsyncClient, db_session):
    # 1. Register candidate
    reg = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "matcher@example.com",
            "password": "Password123!",
            "full_name": "Matcher Candidate",
        },
    )
    user_id = reg.json()["user"]["id"]
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Update candidate profile to require remote and min salary $160,000
    await client.put(
        "/api/v1/profile",
        headers=headers,
        json={
            "remote_preference": "remote",
            "min_salary": 160000,
        },
    )

    # 3. Add confirmed ProfileFacts with skills
    fact = ProfileFact(
        user_id=user_id,
        text="Built high-scale async services with Python and FastAPI",
        category="experience",
        confirmation_status="confirmed",
        entities={"skills": ["Python", "FastAPI", "PostgreSQL"]},
    )
    db_session.add(fact)

    # Also add an unconfirmed candidate fact (which MUST NOT be used)
    unconfirmed = ProfileFact(
        user_id=user_id,
        text="Played around with Go language",
        category="experience",
        confirmation_status="candidate",
        entities={"skills": ["Go"]},
    )
    db_session.add(unconfirmed)
    await db_session.flush()

    matching_service = MatchingService(db_session)

    # TEST CASE A: Hard Filter Elimination (On-site job fails hard filter)
    onsite_job = Job(
        user_id=user_id,
        job_fingerprint="fp_onsite_1",
        title="Onsite Engineer",
        company="Strict Corp",
        description="Must work in office daily",
        remote_type="on-site",
        salary_min=180000,
        salary_max=220000,
        required_skills=["Python"],
    )
    db_session.add(onsite_job)
    await db_session.flush()

    match_a = await matching_service.compute_match(user_id, onsite_job.id)
    assert match_a.hard_filter_passed is False
    assert match_a.score == 0.0
    assert match_a.explanation["recommended_action"] == "skip"

    # TEST CASE B: Hard Filter Elimination (Low salary fails hard filter)
    low_salary_job = Job(
        user_id=user_id,
        job_fingerprint="fp_low_sal_1",
        title="Remote Engineer",
        company="Low Pay LLC",
        description="Remote role with low budget",
        remote_type="remote",
        salary_min=100000,
        salary_max=130000,  # Below candidate's min $160k
        required_skills=["Python"],
    )
    db_session.add(low_salary_job)
    await db_session.flush()

    match_b = await matching_service.compute_match(user_id, low_salary_job.id)
    assert match_b.hard_filter_passed is False
    assert match_b.score == 0.0

    # TEST CASE C: High-Fit Match with Confirmed Skills
    good_job = Job(
        user_id=user_id,
        job_fingerprint="fp_good_1",
        title="Senior Python Backend Engineer",
        company="Great Stripe",
        description="Scale payment APIs",
        remote_type="remote",
        salary_min=170000,
        salary_max=210000,
        required_skills=["Python", "FastAPI"],
        preferred_skills=["PostgreSQL"],
    )
    db_session.add(good_job)
    await db_session.flush()

    match_c = await matching_service.compute_match(user_id, good_job.id)
    assert match_c.hard_filter_passed is True
    assert match_c.score >= 80.0
    assert match_c.confidence >= 0.90
    assert "Python" in match_c.explanation["matched_skills"]
    assert match_c.explanation["recommended_action"] in ["apply", "apply_after_tailoring"]

    # TEST CASE D: Unknown != Match (Undisclosed salary reduces confidence score)
    undisclosed_salary_job = Job(
        user_id=user_id,
        job_fingerprint="fp_undisclosed_1",
        title="Python Engineer No Salary",
        company="Mystery Corp",
        description="Salary not listed",
        remote_type="remote",
        salary_min=None,
        salary_max=None,  # Unknown salary
        required_skills=["Python", "FastAPI"],
    )
    db_session.add(undisclosed_salary_job)
    await db_session.flush()

    match_d = await matching_service.compute_match(user_id, undisclosed_salary_job.id)
    assert match_d.confidence < match_c.confidence, (
        "Undisclosed fields must lower confidence score!"
    )
    assert any(
        "Salary range is undisclosed" in item
        for item in match_d.explanation["missing_or_uncertain"]
    )


def test_matching_eval_harness_metrics_exit_gate():
    """Validates NDCG and Precision metrics across the 50 synthetic evaluation pairs."""
    report = evaluate_matching_engine()
    assert report["dataset_size"] == 50
    assert report["ndcg_at_10"] >= 0.85, (
        f"NDCG@10 ({report['ndcg_at_10']}) dropped below 0.85 tolerance threshold!"
    )
    assert report["precision_at_10"] >= 0.80, (
        f"Precision@10 ({report['precision_at_10']}) dropped below 0.80 tolerance!"
    )
    assert report["spearman_correlation"] >= 0.70, (
        f"Spearman rank correlation ({report['spearman_correlation']}) dropped below 0.70!"
    )
