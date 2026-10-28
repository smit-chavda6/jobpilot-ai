"""Analytics must equal SQL ground truth on seeded data (spec M8 exit gate)."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from app.db import get_sessionmaker
from app.models import Application, ApplicationActivity, Job, JobMatch, User
from app.services.analytics_math import rate, wilson_interval
from tests.conftest import Api


def test_wilson_interval_known_values() -> None:
    lo, hi = wilson_interval(8, 20)
    assert round(lo, 3) == 0.219 and round(hi, 3) == 0.613
    assert wilson_interval(0, 0) == (0.0, 0.0)
    lo, hi = wilson_interval(0, 10)
    assert lo == 0.0 and hi > 0.2


def test_rate_withheld_below_min_n() -> None:
    r = rate(3, 5, 20)
    assert r["insufficient_data"] and r["rate"] is None
    r = rate(10, 40, 20)
    assert r["rate"] == 0.25 and r["ci_low"] < 0.25 < r["ci_high"]


async def _seed(email: str, n_apps: int) -> uuid.UUID:
    async with get_sessionmaker()() as s:
        user_id = (await s.execute(text("SELECT id FROM users WHERE email=:e"), {"e": email})).scalar_one()
        user_id = uuid.UUID(str(user_id)) if not isinstance(user_id, uuid.UUID) else user_id
        base = datetime(2026, 9, 1, tzinfo=UTC)
        for i in range(n_apps):
            job = Job(
                user_id=user_id,
                source="greenhouse" if i % 2 else "manual_paste",
                title=f"Role {i}",
                company=f"Co {i}",
                fingerprint=f"fp{i}",
                is_demo=True,
            )
            s.add(job)
            await s.flush()
            s.add(
                JobMatch(
                    user_id=user_id,
                    job_id=job.id,
                    score=30 + (i * 7) % 70,
                    confidence=0.8,
                    eligible=True,
                    recommended_action="apply",
                    breakdown={},
                    explanation={},
                    config_snapshot={},
                )
            )
            submitted = base + timedelta(days=i)
            status = "submitted_confirmed"
            responded = i % 3 == 0
            interviewed = i % 6 == 0
            if interviewed:
                status = "interviewing"
            elif responded:
                status = "rejected"
            app = Application(
                user_id=user_id,
                job_id=job.id,
                status=status,
                submitted_at=submitted,
                first_response_at=submitted + timedelta(days=i % 10) if responded else None,
                is_demo=True,
            )
            s.add(app)
            await s.flush()
            s.add(
                ApplicationActivity(
                    user_id=user_id,
                    application_id=app.id,
                    action="user_confirmation",
                    from_status="awaiting_user_confirmation",
                    to_status="submitted_confirmed",
                )
            )
            if interviewed:
                s.add(
                    ApplicationActivity(
                        user_id=user_id,
                        application_id=app.id,
                        action="status_changed",
                        from_status="submitted_confirmed",
                        to_status="interviewing",
                    )
                )
        await s.commit()
        return user_id


async def test_analytics_match_sql_ground_truth(api: Api, make_api) -> None:  # type: ignore[no-untyped-def]
    user_id = await _seed("alice@example.com", 30)
    other = await make_api("bob@example.com")
    await _seed("bob@example.com", 5)  # must not leak into alice's numbers

    async with get_sessionmaker()() as s:
        uid = user_id.hex
        q = lambda sql: s.execute(text(sql), {"u": uid})  # noqa: E731
        submitted = (
            await q("SELECT COUNT(*) FROM applications WHERE user_id=:u AND submitted_at IS NOT NULL")
        ).scalar_one()
        responded = (
            await q("SELECT COUNT(*) FROM applications WHERE user_id=:u AND first_response_at IS NOT NULL")
        ).scalar_one()
        interviewed = (
            await q(
                "SELECT COUNT(DISTINCT application_id) FROM application_activities "
                "WHERE user_id=:u AND to_status='interviewing'"
            )
        ).scalar_one()
        by_status = dict((await q("SELECT status, COUNT(*) FROM applications WHERE user_id=:u GROUP BY status")).all())
        gh = (
            await q(
                "SELECT COUNT(*), SUM(CASE WHEN a.first_response_at IS NOT NULL THEN 1 ELSE 0 END) FROM applications a "
                "JOIN jobs j ON j.id=a.job_id WHERE a.user_id=:u AND j.source='greenhouse'"
            )
        ).one()

    a = (await api.get("/api/analytics")).json()
    assert a["totals"]["submitted"] == submitted == 30
    assert a["response_rate"]["n"] == submitted and a["response_rate"]["successes"] == responded
    assert a["response_rate"]["rate"] == round(responded / submitted, 4)
    assert a["interview_rate"]["successes"] == interviewed
    assert a["by_status"] == by_status
    src = {x["source"]: x["response_rate"] for x in a["by_source"]}
    assert src["greenhouse"]["n"] == gh[0] and src["greenhouse"]["successes"] == gh[1]
    assert src["greenhouse"]["insufficient_data"] is True  # n=15 < 20
    assert a["funnel"][0]["count"] == submitted and a["funnel"][1]["count"] == responded
    assert a["time_to_response"]["n"] == responded
    assert sum(b["count"] for b in a["time_to_response"]["buckets"]) == responded
    assert sum(w["count"] for w in a["weekly_submissions"]) == submitted
    assert sum(b["interview_rate"]["n"] for b in a["score_band_vs_interview"]) == submitted
    assert "not show that one causes" in a["note"]
    assert a["totals"]["demo_applications"] == 30
    assert (await api.get("/api/analytics", params={"include_demo": "false"})).json()["totals"]["submitted"] == 0
    assert (await other.get("/api/analytics")).json()["totals"]["submitted"] == 5


async def test_empty_analytics_reports_insufficient_data(api: Api) -> None:
    a = (await api.get("/api/analytics")).json()
    assert a["response_rate"]["insufficient_data"] and a["response_rate"]["rate"] is None


def test_user_model_is_imported() -> None:
    assert User.__tablename__ == "users"
