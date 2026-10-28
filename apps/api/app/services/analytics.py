"""Analytics (spec §13): every metric is computed by SQL over stored records, reports its sample size,
withholds rates below a configurable n, and attaches Wilson 95% intervals. Correlation != causation."""

from __future__ import annotations

import uuid
from collections import Counter
from typing import Any

from sqlalchemy import case, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Application, ApplicationActivity, Job, JobMatch
from app.services.analytics_math import rate

CAUSAL_NOTE = (
    "These figures describe your own history. Correlations (e.g. between match score and interviews) "
    "do not show that one causes the other, and small samples can mislead."
)
SCORE_BANDS = [(0, 40, "0-39"), (40, 55, "40-54"), (55, 75, "55-74"), (75, 101, "75-100")]
RESPONSE_BUCKETS = [
    (0, 3, "0-3 days"),
    (4, 7, "4-7 days"),
    (8, 14, "8-14 days"),
    (15, 30, "15-30 days"),
    (31, 10_000, "31+ days"),
]


async def compute(session: AsyncSession, user_id: uuid.UUID, include_demo: bool = True) -> dict[str, Any]:
    min_n = get_settings().analytics_min_n
    A = Application
    base = [A.user_id == user_id]
    if not include_demo:
        base.append(A.is_demo.is_(False))

    status_rows = (await session.execute(select(A.status, func.count()).where(*base).group_by(A.status))).all()
    by_status = {s: int(c) for s, c in status_rows}

    submitted = int(
        (
            await session.execute(select(func.count()).select_from(A).where(*base, A.submitted_at.is_not(None)))
        ).scalar_one()
    )
    responded = int(
        (
            await session.execute(
                select(func.count())
                .select_from(A)
                .where(*base, A.submitted_at.is_not(None), A.first_response_at.is_not(None))
            )
        ).scalar_one()
    )

    async def reached(statuses: tuple[str, ...]) -> int:
        q = (
            select(func.count(distinct(ApplicationActivity.application_id)))
            .join(A, A.id == ApplicationActivity.application_id)
            .where(*base, ApplicationActivity.to_status.in_(statuses), A.submitted_at.is_not(None))
        )
        return int((await session.execute(q)).scalar_one())

    interviewed = await reached(("interviewing",))
    offers = await reached(("offer",))

    funnel_stages = [
        ("Submitted", submitted),
        ("Got a response", responded),
        ("Interviewed", interviewed),
        ("Offer", offers),
    ]
    funnel = []
    for i, (name, count) in enumerate(funnel_stages):
        prev = funnel_stages[i - 1][1] if i else 0
        funnel.append({"stage": name, "count": count, "drop_off": round(1 - count / prev, 4) if prev else None})

    pairs = (
        await session.execute(
            select(A.submitted_at, A.first_response_at).where(
                *base, A.submitted_at.is_not(None), A.first_response_at.is_not(None)
            )
        )
    ).all()
    days = [max(0, (r - s).days) for s, r in pairs]
    dist: Counter[str] = Counter()
    for d in days:
        for lo, hi, label in RESPONSE_BUCKETS:
            if lo <= d <= hi:
                dist[label] += 1
    median = sorted(days)[len(days) // 2] if days else None

    src_rows = (
        await session.execute(
            select(
                Job.source,
                func.count(),
                func.sum(case((A.first_response_at.is_not(None), 1), else_=0)),
                func.sum(case((A.status.in_(("interviewing", "offer", "accepted")), 1), else_=0)),
            )
            .join(Job, Job.id == A.job_id)
            .where(*base, A.submitted_at.is_not(None))
            .group_by(Job.source)
        )
    ).all()
    by_source = [{"source": s, "response_rate": rate(int(r or 0), int(n), min_n)} for s, n, r, _ in src_rows]

    band_rows = (
        await session.execute(
            select(JobMatch.score, A.status, A.id)
            .join(A, (A.job_id == JobMatch.job_id) & (A.user_id == JobMatch.user_id))
            .where(*base, A.submitted_at.is_not(None))
        )
    ).all()
    interviewed_ids = set(
        (
            await session.execute(
                select(ApplicationActivity.application_id)
                .join(A, A.id == ApplicationActivity.application_id)
                .where(*base, ApplicationActivity.to_status == "interviewing")
            )
        )
        .scalars()
        .all()
    )
    bands = []
    for lo, hi, label in SCORE_BANDS:
        rows = [r for r in band_rows if lo <= r[0] < hi]
        bands.append(
            {"band": label, "interview_rate": rate(sum(1 for r in rows if r[2] in interviewed_ids), len(rows), min_n)}
        )

    week_rows = (
        (await session.execute(select(A.submitted_at).where(*base, A.submitted_at.is_not(None)))).scalars().all()
    )
    weekly = Counter(f"{d.isocalendar().year}-W{d.isocalendar().week:02d}" for d in week_rows if d is not None)

    jobs_total = int(
        (await session.execute(select(func.count()).select_from(Job).where(Job.user_id == user_id))).scalar_one()
    )
    demo_apps = int(
        (
            await session.execute(select(func.count()).select_from(A).where(A.user_id == user_id, A.is_demo.is_(True)))
        ).scalar_one()
    )

    return {
        "totals": {
            "jobs": jobs_total,
            "applications": sum(by_status.values()),
            "submitted": submitted,
            "demo_applications": demo_apps,
            "include_demo": include_demo,
        },
        "by_status": by_status,
        "response_rate": rate(responded, submitted, min_n),
        "interview_rate": rate(interviewed, submitted, min_n),
        "offer_rate": rate(offers, submitted, min_n),
        "funnel": funnel,
        "time_to_response": {
            "n": len(days),
            "median_days": median,
            "buckets": [{"bucket": label, "count": dist.get(label, 0)} for _, _, label in RESPONSE_BUCKETS],
        },
        "by_source": by_source,
        "score_band_vs_interview": bands,
        "weekly_submissions": [{"week": w, "count": c} for w, c in sorted(weekly.items())],
        "min_n": min_n,
        "note": CAUSAL_NOTE,
    }
