"""Application workflow orchestrator with strict state machine, cryptographic approval hashing, and human confirmation gates."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models.application import Application, ApplicationActivity, ScreeningAnswer
from apps.api.models.security import ApprovalRecord
from apps.api.repositories.application_repository import ApplicationRepository


class StateTransitionError(Exception):
    """Raised when an illegal status transition is requested."""
    pass


class DuplicateApplicationError(Exception):
    """Raised when attempting to create a second application for the same job."""
    pass


class HumanConfirmationRequiredError(Exception):
    """Raised when a final submission is attempted without explicit human confirmation."""
    pass


class UnapprovedPayloadError(Exception):
    """Raised when application payload does not match cryptographic approval hash."""
    pass


# Strict State Machine Transition Matrix
VALID_TRANSITIONS: Dict[str, Set[str]] = {
    "saved": {"preparing", "withdrawn"},
    "discovered": {"saved", "preparing", "withdrawn"},
    "preparing": {"ready_for_review", "saved", "withdrawn"},
    "ready_for_review": {"approved", "preparing", "withdrawn"},
    "approved": {"submitting", "ready_for_review", "withdrawn"},
    "submitting": {"submitted_confirmed", "ready_for_review", "withdrawn"},
    "submitted_confirmed": {"interviewing", "rejected", "offer", "withdrawn"},
    "interviewing": {"offer", "rejected", "withdrawn"},
    "offer": {"withdrawn"},
    "rejected": set(),
    "withdrawn": {"saved"},
}


def compute_payload_hash(payload: Dict[str, Any]) -> str:
    """Deterministic SHA-256 hash of application submission payload."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ApplicationWorkflowService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = ApplicationRepository(session)

    async def create_application(
        self, user_id: str, job_id: str, notes: Optional[str] = None
    ) -> Application:
        """Create new application in 'saved' state. Strictly blocks duplicates."""
        existing = await self.repo.get_by_job_id(user_id, job_id)
        if existing:
            raise DuplicateApplicationError(
                f"Application already exists for job '{job_id}' in state '{existing.status}'."
            )

        app = Application(
            user_id=user_id,
            job_id=job_id,
            status="saved",
            notes=notes,
        )
        await self.repo.create(app)

        activity = ApplicationActivity(
            application_id=app.id,
            user_id=user_id,
            from_status=None,
            to_status="saved",
            activity_type="created",
            message="Application saved to tracker.",
            activity_metadata={"job_id": job_id},
        )
        await self.repo.add_activity(activity)
        return app

    def build_application_payload(self, app: Application) -> Dict[str, Any]:
        """Construct canonical dictionary representation of application materials."""
        return {
            "application_id": app.id,
            "job_id": app.job_id,
            "resume_version_id": app.resume_version_id,
            "cover_letter": app.cover_letter or "",
            "screening_answers": [
                {"question": sa.question, "answer": sa.answer}
                for sa in (app.screening_answers or [])
            ],
            "external_url": app.external_url or "",
        }

    async def get_latest_approval(self, user_id: str, app_id: str) -> Optional[ApprovalRecord]:
        """Fetch latest approval record for this application."""
        stmt = (
            select(ApprovalRecord)
            .where(
                ApprovalRecord.user_id == user_id,
                ApprovalRecord.entity_id == app_id,
                ApprovalRecord.action_type == "application_submission",
            )
            .order_by(ApprovalRecord.approved_at.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def update_payload(
        self,
        user_id: str,
        app_id: str,
        resume_version_id: Optional[str] = None,
        cover_letter: Optional[str] = None,
        notes: Optional[str] = None,
        external_url: Optional[str] = None,
    ) -> Application:
        """Update materials. If application was approved, modifications immediately invalidate approval."""
        app = await self.repo.get_by_id(user_id, app_id)
        if not app:
            raise ValueError("Application not found")

        was_approved = app.status in ["approved", "submitting"]

        if resume_version_id is not None:
            app.resume_version_id = resume_version_id
        if cover_letter is not None:
            app.cover_letter = cover_letter
        if notes is not None:
            app.notes = notes
        if external_url is not None:
            app.external_url = external_url

        # CRITICAL INVARIANT: Modification invalidates approval and returns to ready_for_review
        if was_approved:
            old_status = app.status
            app.status = "ready_for_review"
            activity = ApplicationActivity(
                application_id=app.id,
                user_id=user_id,
                from_status=old_status,
                to_status="ready_for_review",
                activity_type="approval_invalidated",
                message="Application payload modified after approval; approval invalidated and reverted to review.",
                activity_metadata={"previous_status": old_status},
            )
            await self.repo.add_activity(activity)

        await self.session.flush()
        return app

    async def approve_application(
        self,
        user_id: str,
        app_id: str,
        confirmed_by_user: bool = False,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Tuple[Application, ApprovalRecord]:
        """Cryptographically sign and approve submission package."""
        if not confirmed_by_user:
            raise HumanConfirmationRequiredError(
                "Explicit human approval confirmation required before signing payload."
            )

        app = await self.repo.get_by_id(user_id, app_id)
        if not app:
            raise ValueError("Application not found")

        if app.status not in ["ready_for_review", "preparing"]:
            raise StateTransitionError(
                f"Cannot approve application in status '{app.status}'. Must be 'ready_for_review'."
            )

        payload = self.build_application_payload(app)
        payload_hash = compute_payload_hash(payload)

        approval = ApprovalRecord(
            user_id=user_id,
            action_type="application_submission",
            entity_id=app.id,
            payload_hash=payload_hash,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.session.add(approval)

        old_status = app.status
        app.status = "approved"

        activity = ApplicationActivity(
            application_id=app.id,
            user_id=user_id,
            from_status=old_status,
            to_status="approved",
            activity_type="approved",
            message=f"Application package approved by user. Cryptographic hash: {payload_hash[:16]}...",
            activity_metadata={"payload_hash": payload_hash},
        )
        await self.repo.add_activity(activity)
        await self.session.flush()

        return app, approval

    async def transition_status(
        self,
        user_id: str,
        app_id: str,
        target_status: str,
        confirmed_by_user: bool = False,
        notes: Optional[str] = None,
    ) -> Application:
        """Safely transition application state checking guards and approval hashes."""
        app = await self.repo.get_by_id(user_id, app_id)
        if not app:
            raise ValueError("Application not found")

        current_status = app.status

        # 1. Validate State Machine Graph
        allowed = VALID_TRANSITIONS.get(current_status, set())
        if target_status not in allowed:
            raise StateTransitionError(
                f"Illegal state transition from '{current_status}' to '{target_status}'. Allowed: {sorted(list(allowed))}"
            )

        # 2. Strict Submission Gates
        if target_status == "submitted_confirmed":
            # Human confirmation mandatory
            if not confirmed_by_user:
                raise HumanConfirmationRequiredError(
                    "Transition to 'submitted_confirmed' requires explicit user confirmation (human-in-the-loop)."
                )

            # Cryptographic approval check
            latest_approval = await self.get_latest_approval(user_id, app.id)
            if not latest_approval:
                raise UnapprovedPayloadError(
                    "Cannot mark as submitted_confirmed: No cryptographic ApprovalRecord found."
                )

            current_payload = self.build_application_payload(app)
            current_hash = compute_payload_hash(current_payload)
            if current_hash != latest_approval.payload_hash:
                raise UnapprovedPayloadError(
                    "Cannot submit: Application payload was modified after approval. Re-approval required."
                )

            app.applied_at = datetime.now(timezone.utc).isoformat()

        # Update status
        app.status = target_status
        if notes:
            app.notes = (app.notes or "") + f"\n[{datetime.now(timezone.utc).strftime('%Y-%m-%d')}]: {notes}"

        # Record activity log
        activity = ApplicationActivity(
            application_id=app.id,
            user_id=user_id,
            from_status=current_status,
            to_status=target_status,
            activity_type="status_change",
            message=f"Status transitioned from {current_status} to {target_status}." + (f" Notes: {notes}" if notes else ""),
            activity_metadata={"confirmed_by_user": confirmed_by_user},
        )
        await self.repo.add_activity(activity)
        await self.session.flush()

        return app

    async def check_follow_up_reminders(
        self, user_id: str, days_threshold: int = 7
    ) -> List[Dict[str, Any]]:
        """Identify applications submitted more than days_threshold ago without updates."""
        apps = await self.repo.list_by_user(user_id, status="submitted_confirmed")
        reminders = []
        now = datetime.now(timezone.utc)

        for app in apps:
            if not app.applied_at:
                continue
            try:
                applied_date = datetime.fromisoformat(app.applied_at)
            except Exception:
                continue

            days_elapsed = (now - applied_date).days
            if days_elapsed >= days_threshold:
                reminders.append({
                    "application_id": app.id,
                    "job_id": app.job_id,
                    "company": app.job.company if app.job else "Target Company",
                    "title": app.job.title if app.job else "Target Role",
                    "applied_at": app.applied_at,
                    "days_since_submission": days_elapsed,
                    "recommended_action": f"Send polite follow-up email ({days_elapsed} days elapsed).",
                })

        return reminders
