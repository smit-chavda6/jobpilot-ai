"""Comprehensive tests for M7: Application Workflow, State Machine, Cryptographic Approvals, and Reminders."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models.application import Application, ApplicationActivity
from apps.api.models.job import Job
from apps.api.models.user import User
from apps.api.services.application_workflow_service import (
    ApplicationWorkflowService,
    DuplicateApplicationError,
    HumanConfirmationRequiredError,
    StateTransitionError,
    UnapprovedPayloadError,
)


@pytest.fixture
async def workflow_setup(db_session: AsyncSession):
    user = User(
        email="workflow_candidate@example.com",
        hashed_password="hashed_pw_test",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    job = Job(
        user_id=user.id,
        job_fingerprint="stripe-staff-infra",
        title="Staff Infrastructure Engineer",
        company="Stripe",
        location="Remote",
        remote_type="remote",
        description="Lead global infra scaling.",
        required_skills=["python", "kubernetes"],
    )
    db_session.add(job)
    await db_session.flush()

    return user, job


@pytest.mark.asyncio
async def test_duplicate_application_blocked(workflow_setup, db_session: AsyncSession):
    user, job = workflow_setup
    svc = ApplicationWorkflowService(db_session)

    # 1. First application succeeds in 'saved' state
    app1 = await svc.create_application(user.id, job.id, notes="Interested in infra team")
    assert app1.id is not None
    assert app1.status == "saved"

    # 2. Duplicate application for same user and job MUST be blocked
    with pytest.raises(DuplicateApplicationError):
        await svc.create_application(user.id, job.id, notes="Duplicate attempt")


@pytest.mark.asyncio
async def test_state_machine_transition_guards_and_illegal_transitions(
    workflow_setup, db_session: AsyncSession
):
    user, job = workflow_setup
    svc = ApplicationWorkflowService(db_session)

    app = await svc.create_application(user.id, job.id)

    # Illegal transition: 'saved' directly to 'submitted_confirmed'
    with pytest.raises(StateTransitionError):
        await svc.transition_status(user.id, app.id, "submitted_confirmed", confirmed_by_user=True)

    # Illegal transition: 'saved' to 'approved'
    with pytest.raises(StateTransitionError):
        await svc.transition_status(user.id, app.id, "approved")

    # Legal progression: saved -> preparing -> ready_for_review
    app = await svc.transition_status(user.id, app.id, "preparing")
    assert app.status == "preparing"

    app = await svc.transition_status(user.id, app.id, "ready_for_review")
    assert app.status == "ready_for_review"


@pytest.mark.asyncio
async def test_human_confirmation_and_approval_payload_hash_lifecycle(
    workflow_setup, db_session: AsyncSession
):
    user, job = workflow_setup
    svc = ApplicationWorkflowService(db_session)

    app = await svc.create_application(user.id, job.id)
    await svc.transition_status(user.id, app.id, "preparing")
    await svc.transition_status(user.id, app.id, "ready_for_review")

    # 1. Approval requires explicit human confirmation
    with pytest.raises(HumanConfirmationRequiredError):
        await svc.approve_application(user.id, app.id, confirmed_by_user=False)

    # 2. Human confirms approval -> creates ApprovalRecord with cryptographic payload hash
    app, approval = await svc.approve_application(user.id, app.id, confirmed_by_user=True)
    assert app.status == "approved"
    assert approval.payload_hash is not None
    assert len(approval.payload_hash) == 64  # SHA-256 hex length

    # 3. Transition to 'submitting'
    app = await svc.transition_status(user.id, app.id, "submitting")
    assert app.status == "submitting"

    # 4. CRITICAL INVARIANT: Modifying payload invalidates approval and reverts to ready_for_review
    app = await svc.update_payload(
        user.id,
        app.id,
        cover_letter="Changed cover letter content after approval was granted.",
    )
    assert app.status == "ready_for_review"

    # 5. Cannot jump straight to submitted_confirmed with altered unapproved payload
    with pytest.raises(StateTransitionError):
        await svc.transition_status(user.id, app.id, "submitted_confirmed", confirmed_by_user=True)

    # 6. Re-approve altered payload
    app, new_approval = await svc.approve_application(user.id, app.id, confirmed_by_user=True)
    assert app.status == "approved"
    assert new_approval.payload_hash != approval.payload_hash  # Hash changed due to modified cover letter

    # 7. Progress to submitting
    app = await svc.transition_status(user.id, app.id, "submitting")

    # 8. Attempting submitted_confirmed WITHOUT confirmed_by_user=True is strictly blocked
    with pytest.raises(HumanConfirmationRequiredError):
        await svc.transition_status(user.id, app.id, "submitted_confirmed", confirmed_by_user=False)

    # 9. Successfully submit with confirmed_by_user=True
    app = await svc.transition_status(user.id, app.id, "submitted_confirmed", confirmed_by_user=True)
    assert app.status == "submitted_confirmed"
    assert app.applied_at is not None


@pytest.mark.asyncio
async def test_audit_activity_trail_and_reminder_scheduler(
    workflow_setup, db_session: AsyncSession
):
    user, job = workflow_setup
    svc = ApplicationWorkflowService(db_session)

    app = await svc.create_application(user.id, job.id)
    await svc.transition_status(user.id, app.id, "preparing")
    await svc.transition_status(user.id, app.id, "ready_for_review")
    await svc.approve_application(user.id, app.id, confirmed_by_user=True)
    await svc.transition_status(user.id, app.id, "submitting")
    await svc.transition_status(user.id, app.id, "submitted_confirmed", confirmed_by_user=True)

    # Verify audit activity entries exist in sequence
    stmt = select(ApplicationActivity).where(ApplicationActivity.application_id == app.id)
    res = await db_session.execute(stmt)
    activities = list(res.scalars().all())
    assert len(activities) >= 5
    assert any(a.activity_type == "approved" for a in activities)
    assert any(a.to_status == "submitted_confirmed" for a in activities)

    # Verify Reminder Scheduler
    # Simulate submission 8 days ago
    eight_days_ago = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    app.applied_at = eight_days_ago
    await db_session.flush()

    reminders = await svc.check_follow_up_reminders(user.id, days_threshold=7)
    assert len(reminders) == 1
    assert reminders[0]["application_id"] == app.id
    assert reminders[0]["days_since_submission"] >= 8
    assert "follow-up" in reminders[0]["recommended_action"].lower()
