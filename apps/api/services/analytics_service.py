"""SQL-backed analytics engine with Wilson score confidence intervals and honest small-sample statistics."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models.application import Application, ApplicationActivity


def wilson_score_interval(
    successes: int, total: int, z: float = 1.96
) -> Dict[str, Any]:
    """Calculate 95% Wilson score confidence interval for a binomial proportion."""
    if total == 0:
        return {
            "point_estimate": 0.0,
            "ci_lower": 0.0,
            "ci_upper": 0.0,
            "sample_size": 0,
            "small_sample_warning": True,
            "disclaimer": "Sample size is 0. No statistical inference can be made.",
        }

    p = successes / total
    denom = 1 + (z**2 / total)
    center = (p + (z**2 / (2 * total))) / denom
    spread = (z * math.sqrt((p * (1 - p) / total) + (z**2 / (4 * total**2)))) / denom

    lower = max(0.0, round(center - spread, 3))
    upper = min(1.0, round(center + spread, 3))
    point = round(p, 3)

    is_small = total < 30
    disclaimer = (
        f"Sample size (n={total}) is small (n < 30). Wilson 95% CI is wide [{lower*100:.1f}%, {upper*100:.1f}%]; interpret with caution."
        if is_small
        else f"Statistically robust sample size (n={total}). 95% CI: [{lower*100:.1f}%, {upper*100:.1f}%]."
    )

    return {
        "point_estimate": point,
        "ci_lower": lower,
        "ci_upper": upper,
        "sample_size": total,
        "small_sample_warning": is_small,
        "disclaimer": disclaimer,
    }


class AnalyticsService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_funnel_and_conversion_metrics(self, user_id: str) -> Dict[str, Any]:
        """Compute application funnel stages and response rate with Wilson intervals."""
        # 1. Total saved / discovered
        stmt_total = select(func.count(Application.id)).where(Application.user_id == user_id)
        total_tracked = (await self.session.execute(stmt_total)).scalar() or 0

        # 2. Total submitted
        submitted_statuses = ["submitted_confirmed", "interviewing", "offer", "rejected"]
        stmt_sub = select(func.count(Application.id)).where(
            Application.user_id == user_id,
            Application.status.in_(submitted_statuses),
        )
        total_submitted = (await self.session.execute(stmt_sub)).scalar() or 0

        # 3. Total interviews
        interview_statuses = ["interviewing", "offer"]
        stmt_int = select(func.count(Application.id)).where(
            Application.user_id == user_id,
            Application.status.in_(interview_statuses),
        )
        total_interviewing = (await self.session.execute(stmt_int)).scalar() or 0

        # 4. Total offers
        stmt_off = select(func.count(Application.id)).where(
            Application.user_id == user_id,
            Application.status == "offer",
        )
        total_offers = (await self.session.execute(stmt_off)).scalar() or 0

        # 5. Tailored vs Default breakdown
        stmt_tailored = select(func.count(Application.id)).where(
            Application.user_id == user_id,
            Application.status.in_(submitted_statuses),
            Application.resume_version_id.isnot(None),
        )
        tailored_submitted = (await self.session.execute(stmt_tailored)).scalar() or 0

        stmt_tailored_int = select(func.count(Application.id)).where(
            Application.user_id == user_id,
            Application.status.in_(interview_statuses),
            Application.resume_version_id.isnot(None),
        )
        tailored_interviews = (await self.session.execute(stmt_tailored_int)).scalar() or 0

        default_submitted = total_submitted - tailored_submitted
        default_interviews = total_interviewing - tailored_interviews

        # Wilson intervals
        overall_conversion = wilson_score_interval(total_interviewing, total_submitted)
        tailored_conversion = wilson_score_interval(tailored_interviews, tailored_submitted)
        default_conversion = wilson_score_interval(default_interviews, default_submitted)

        return {
            "funnel": {
                "saved_tracked": total_tracked,
                "submitted": total_submitted,
                "interviewing": total_interviewing,
                "offers": total_offers,
            },
            "overall_response_rate": overall_conversion,
            "tailored_vs_default": {
                "tailored": {
                    "submitted": tailored_submitted,
                    "interviews": tailored_interviews,
                    "metrics": tailored_conversion,
                },
                "default": {
                    "submitted": default_submitted,
                    "interviews": default_interviews,
                    "metrics": default_conversion,
                },
            },
            "interpretation_note": "Wilson score intervals provide honest confidence ranges rather than misleading point percentages when candidate sample size is low.",
        }
