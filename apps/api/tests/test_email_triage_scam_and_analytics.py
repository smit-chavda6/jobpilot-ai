"""Tests for M8: Email Triage Classifier, Scam Signal Engine, Interview Prep, and Analytics."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models.application import Application
from apps.api.models.fact import ProfileFact
from apps.api.models.job import Job
from apps.api.models.user import User
from apps.api.services.analytics_service import AnalyticsService, wilson_score_interval
from apps.api.services.email_triage_service import EmailTriageService
from apps.api.services.interview_prep_service import InterviewPrepService
from apps.api.services.scam_detection_service import ScamDetectionService


# =====================================================================
# 1. Synthetic .eml Classification Test Suite (Exit Gate: >=90% accuracy)
# =====================================================================

SYNTHETIC_EMAIL_CORPUS = [
    # Interview Invites
    ("Invitation to Interview: Senior Backend Engineer at Stripe", "Hi Elena, we would love to schedule a call with the hiring manager via Calendly.", "interview_invite"),
    ("Next Round: Interview with Coinbase Engineering Team", "Please let us know your availability for a 45-minute video call interview next week.", "interview_invite"),
    ("Phone Screen Availability - Datadog", "Are you available for an initial phone screen chat with our recruiting team?", "interview_invite"),

    # Rejections
    ("Update on your application at Airbnb", "Thank you for applying. Unfortunately, after careful consideration, we are not moving forward with your candidacy.", "rejection"),
    ("Your candidacy at Netflix", "We regret to inform you that we have decided to pursue other candidates who more closely match our requirements.", "rejection"),
    ("Application status for Software Engineer at Figma", "Due to a high volume of applicants, you were not selected for this role. We wish you the best in your job search.", "rejection"),

    # Offers
    ("Formal Offer Letter: Senior Engineer at GitHub", "Congratulations! We are pleased to offer you the position. Please review the attached compensation package.", "offer"),
    ("Job Offer - Welcome to the Team at Retool", "We are thrilled to extend a formal offer letter to join Retool as Senior Staff Engineer.", "offer"),

    # Assessment Requests
    ("Complete Your Technical Assessment - HackerRank Challenge", "Please complete this 90-minute coding challenge and online assessment within 5 days.", "assessment_request"),
    ("CodeSignal Technical Assessment for Ramp", "You have been invited to complete a technical assessment on CodeSignal for the Backend position.", "assessment_request"),

    # Status Updates
    ("We received your application at Linear", "This email is confirming receipt of your application. Our team is actively reviewing applications.", "status_update"),
    ("Application received - OpenAI", "Thank you for applying to OpenAI. Your profile is currently under review by our talent team.", "status_update"),

    # Marketing / Other
    ("Monthly Tech Talent Trends Newsletter", "Check out the latest salary reports and industry hiring trends for Q4.", "marketing_or_other"),
    ("Webinar: Scaling Cloud Infrastructure in 2026", "Join our virtual panel discussing AI infrastructure architectures.", "marketing_or_other"),
]


def test_email_triage_classifier_accuracy_exit_gate():
    """Exit gate assertion: >= 90% accuracy across synthetic emails."""
    correct = 0
    total = len(SYNTHETIC_EMAIL_CORPUS)

    for subject, body, expected_intent in SYNTHETIC_EMAIL_CORPUS:
        result = EmailTriageService.classify_email(subject, body)
        predicted = result["intent"]
        if predicted == expected_intent:
            correct += 1

    accuracy = correct / total
    assert accuracy >= 0.90, f"Email triage accuracy {accuracy*100:.1f}% fell below 90% threshold!"


def test_eml_mime_parser_extraction():
    raw_eml = (
        b"From: recruiter@stripe.com\r\n"
        b"To: candidate@example.com\r\n"
        b"Subject: Invitation to Interview at Stripe\r\n"
        b"Date: Mon, 12 Oct 2026 10:00:00 +0000\r\n"
        b"Content-Type: text/plain; charset=utf-8\r\n\r\n"
        b"Hi Candidate,\nWe would like to invite you to interview for the role."
    )
    parsed = EmailTriageService.parse_eml_content(raw_eml)
    assert parsed["subject"] == "Invitation to Interview at Stripe"
    assert "recruiter@stripe.com" in parsed["sender"]
    assert "invite you to interview" in parsed["body"]


# =====================================================================
# 2. Scam Detection Service Test
# =====================================================================

def test_scam_detection_signals_transparent_evidence():
    # 1. High risk scam listing with payment and Telegram
    scam_result = ScamDetectionService.evaluate_job(
        title="Entry Level Virtual Assistant",
        company="Global Enterprise LLC",
        description="Immediate hire without interview! We will send a check to purchase equipment from our vendor. Contact our hiring manager on Telegram @hire_now.",
        contact_email="enterprise.recruiting@gmail.com",
        salary_max=350000,
    )
    assert scam_result["is_suspicious"] is True
    assert scam_result["risk_level"] == "high"
    assert scam_result["risk_score"] >= 0.70

    signals = [f["signal"] for f in scam_result["flags"]]
    assert "PAYMENT_OR_CHECK_REQUEST" in signals
    assert "SUSPICIOUS_COMMUNICATION_CHANNEL" in signals
    assert "FREE_MAIL_DOMAIN" in signals
    assert "UNREALISTIC_SALARY" in signals

    # 2. Legitimate engineering job listing
    clean_result = ScamDetectionService.evaluate_job(
        title="Senior Backend Engineer",
        company="Figma",
        description="Figma is seeking an experienced Backend Engineer to work on real-time multiplayer systems using Rust, Go, and PostgreSQL. Candidates should have 5+ years experience building distributed web services with high concurrency.",
        contact_email="recruiting@figma.com",
        salary_max=190000,
    )
    assert clean_result["is_suspicious"] is False
    assert clean_result["risk_level"] == "low"
    assert len(clean_result["flags"]) == 0


# =====================================================================
# 3. Interview Prep STAR Scaffolds Test
# =====================================================================

def test_interview_prep_star_scaffolds_grounded():
    job = Job(
        id="job-prep-1",
        user_id="user-1",
        job_fingerprint="fp-prep",
        title="Senior Systems Engineer",
        company="Scale AI",
        description="Scale AI high throughput systems.",
        required_skills=["python", "fastapi"],
    )
    fact1 = ProfileFact(
        id="fact-star-1",
        user_id="user-1",
        text="Architected distributed cache invalidation serving 10k RPS with 99.99% uptime.",
        category="experience",
        confirmation_status="confirmed",
        entities={"company": "Vercel", "metrics": ["10k RPS", "99.99%"]},
    )

    kit = InterviewPrepService.generate_prep_kit(job, [fact1])
    assert kit["verified_facts_used"] == 1
    scaffold = kit["star_scaffolds"][0]
    assert scaffold["cited_fact_id"] == "fact-star-1"
    assert "Vercel" in scaffold["star"]["situation"]
    assert "10k RPS" in scaffold["star"]["result"]
    assert len(kit["technical_questions"]) >= 2
    assert len(kit["questions_for_interviewer"]) >= 2


# =====================================================================
# 4. Statistical Analytics & Wilson Score Interval Test
# =====================================================================

def test_wilson_score_interval_mathematical_properties():
    # 1. Zero sample size
    w0 = wilson_score_interval(0, 0)
    assert w0["sample_size"] == 0
    assert w0["ci_lower"] == 0.0 and w0["ci_upper"] == 0.0

    # 2. Small sample: 3 successes out of 5 (60% point estimate)
    # Wilson interval should be wide and warn user honestly
    w5 = wilson_score_interval(3, 5)
    assert w5["point_estimate"] == 0.60
    assert w5["small_sample_warning"] is True
    assert w5["ci_lower"] < 0.35  # wide lower bound
    assert w5["ci_upper"] > 0.80  # wide upper bound

    # 3. Large sample: 40 successes out of 100 (40% point estimate)
    w100 = wilson_score_interval(40, 100)
    assert w100["point_estimate"] == 0.40
    assert w100["small_sample_warning"] is False
    assert 0.30 <= w100["ci_lower"] <= 0.35
    assert 0.45 <= w100["ci_upper"] <= 0.52


@pytest.mark.asyncio
async def test_analytics_service_sql_ground_truth(db_session: AsyncSession):
    user = User(
        email="analytics_user@example.com",
        hashed_password="pw_hash_test",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    job1 = Job(
        user_id=user.id,
        job_fingerprint="job-ana-1",
        title="Engineer 1",
        company="Co 1",
        description="JD 1",
    )
    job2 = Job(
        user_id=user.id,
        job_fingerprint="job-ana-2",
        title="Engineer 2",
        company="Co 2",
        description="JD 2",
    )
    db_session.add_all([job1, job2])
    await db_session.flush()

    # Application 1: Submitted with tailored resume
    app1 = Application(
        user_id=user.id,
        job_id=job1.id,
        status="interviewing",
        resume_version_id="custom-v1",
        applied_at="2026-10-01T00:00:00Z",
    )
    # Application 2: Saved only
    app2 = Application(
        user_id=user.id,
        job_id=job2.id,
        status="saved",
    )
    db_session.add_all([app1, app2])
    await db_session.flush()

    svc = AnalyticsService(db_session)
    metrics = await svc.get_funnel_and_conversion_metrics(user.id)

    assert metrics["funnel"]["saved_tracked"] == 2
    assert metrics["funnel"]["submitted"] == 1
    assert metrics["funnel"]["interviewing"] == 1
    assert metrics["tailored_vs_default"]["tailored"]["submitted"] == 1
    assert metrics["tailored_vs_default"]["tailored"]["interviews"] == 1
    assert metrics["tailored_vs_default"]["default"]["submitted"] == 0
