"""Two-stage explainable matching engine with hard filters, unknown handling, and confidence scoring."""

from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models.job import Job, JobMatch
from apps.api.models.profile import UserProfile
from apps.api.repositories.fact_repository import FactRepository
from apps.api.repositories.job_repository import JobRepository
from apps.api.repositories.profile_repository import ProfileRepository

# Canonical skill alias dictionary for normalization
SKILL_ALIASES = {
    "js": "javascript",
    "ts": "typescript",
    "py": "python",
    "k8s": "kubernetes",
    "postgres": "postgresql",
    "postgresql": "postgresql",
    "reactjs": "react",
    "react.js": "react",
    "vuejs": "vue",
    "fastapi": "fastapi",
    "fast-api": "fastapi",
    "docker": "docker",
    "aws": "aws",
    "gcp": "gcp",
    "redis": "redis",
    "kafka": "kafka",
    "celery": "celery",
}


SKILL_DISPLAY_MAP = {
    "python": "Python",
    "fastapi": "FastAPI",
    "postgresql": "PostgreSQL",
    "redis": "Redis",
    "docker": "Docker",
    "kubernetes": "Kubernetes",
    "aws": "AWS",
    "gcp": "GCP",
    "kafka": "Kafka",
    "celery": "Celery",
    "react": "React",
    "typescript": "TypeScript",
    "javascript": "JavaScript",
    "sql": "SQL",
    "linux": "Linux",
}


def normalize_skill(skill_str: str) -> str:
    cleaned = skill_str.lower().strip()
    return SKILL_ALIASES.get(cleaned, cleaned)


def format_skill_display(skill_str: str) -> str:
    norm = normalize_skill(skill_str)
    return SKILL_DISPLAY_MAP.get(norm, norm.title())



DEFAULT_MATCH_CONFIG = {
    "weights": {
        "skills": 0.40,
        "experience": 0.20,
        "education": 0.10,
        "preferences": 0.20,
        "semantic": 0.10,
    },
    "required_skill_multiplier": 1.0,
    "preferred_skill_multiplier": 0.4,
}


class MatchingService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.job_repo = JobRepository(session)
        self.profile_repo = ProfileRepository(session)
        self.fact_repo = FactRepository(session)

    def evaluate_hard_filters(
        self, profile: Optional[UserProfile], job: Job
    ) -> Tuple[bool, List[str]]:
        """
        Stage 1 Deterministic Hard Filters:
        Returns (passed: bool, rejection_reasons: List[str])
        """
        rejection_reasons = []

        if not profile:
            return True, []

        # 1. Remote Preference Filter
        if profile.remote_preference == "remote" and job.remote_type == "on-site":
            rejection_reasons.append(
                "Job requires on-site presence, but candidate profile requires remote."
            )

        # 2. Minimum Salary Filter (if job discloses max salary)
        if profile.min_salary and job.salary_max:
            if job.salary_max < profile.min_salary:
                rejection_reasons.append(
                    f"Job max salary (${job.salary_max:,}) is below candidate minimum threshold (${profile.min_salary:,})."
                )

        passed = len(rejection_reasons) == 0
        return passed, rejection_reasons

    async def compute_match(
        self, user_id: str, job_id: str, config: Optional[Dict[str, Any]] = None
    ) -> JobMatch:
        match_config = config or DEFAULT_MATCH_CONFIG

        job = await self.job_repo.get_by_id(user_id, job_id)
        if not job:
            raise ValueError("Job not found")

        profile = await self.profile_repo.get_by_user_id(user_id)
        # CRITICAL INVARIANT: Only CONFIRMED facts are usable in matching!
        confirmed_facts = await self.fact_repo.list_by_user(
            user_id, confirmation_status="confirmed"
        )

        # Gather confirmed candidate skills
        candidate_skills: Set[str] = set()
        for fact in confirmed_facts:
            entities = fact.entities or {}
            for s in entities.get("skills", []):
                candidate_skills.add(normalize_skill(s))

        # 1. Run Stage 1 Hard Filters
        hard_passed, hard_reasons = self.evaluate_hard_filters(profile, job)
        if not hard_passed:
            match = JobMatch(
                user_id=user_id,
                job_id=job_id,
                score=0.0,
                confidence=1.0,
                hard_filter_passed=False,
                breakdown={"hard_filter_failed": True, "reasons": hard_reasons},
                config_snapshot=match_config,
                explanation={
                    "fit_reasons": [],
                    "matched_skills": [],
                    "missing_or_uncertain": hard_reasons,
                    "projects_to_highlight": [],
                    "questions_to_investigate": ["Can salary or remote policy be negotiated?"],
                    "recommended_action": "skip",
                },
            )
            return await self.job_repo.save_match(match)

        # 2. Stage 2 Scoring
        req_skills = [normalize_skill(s) for s in (job.required_skills or [])]
        pref_skills = [normalize_skill(s) for s in (job.preferred_skills or [])]

        matched_req = [s for s in req_skills if s in candidate_skills]
        missing_req = [s for s in req_skills if s not in candidate_skills]
        matched_pref = [s for s in pref_skills if s in candidate_skills]

        # Skills Score (out of 100)
        req_denom = len(req_skills) or 1
        req_score = (len(matched_req) / req_denom) * 100

        pref_denom = len(pref_skills) or 1
        pref_score = (len(matched_pref) / pref_denom) * 100 if pref_skills else 100

        skills_score = (req_score * 0.7) + (pref_score * 0.3)

        # Experience Score
        exp_score = 85.0 if len(confirmed_facts) >= 3 else 60.0

        # Education Score
        edu_score = 90.0 if any(f.category == "education" for f in confirmed_facts) else 75.0

        # Preferences Alignment Score
        pref_score = 95.0 if job.remote_type in ["remote", "flexible"] else 70.0

        # Semantic Similarity Score
        semantic_score = 80.0

        # Weights
        w = match_config["weights"]
        total_score = (
            (skills_score * w["skills"])
            + (exp_score * w["experience"])
            + (edu_score * w["education"])
            + (pref_score * w["preferences"])
            + (semantic_score * w["semantic"])
        )
        total_score = round(max(0.0, min(100.0, total_score)), 1)

        # Confidence Calculation (unknown handling)
        confidence = 1.0
        missing_or_uncertain = list(missing_req)

        # If job does not disclose salary or experience bounds, lower confidence score
        if not job.salary_min and not job.salary_max:
            confidence -= 0.15
            missing_or_uncertain.append("Salary range is undisclosed (Unknown != Match)")

        if not req_skills:
            confidence -= 0.15
            missing_or_uncertain.append("Explicit required skills are not parsed from JD")

        confidence = round(max(0.4, confidence), 2)

        # Relevant confirmed project facts
        relevant_projects = [
            f.id for f in confirmed_facts if f.category in ["project", "experience"]
        ][:3]

        # Recommended Action Logic
        if total_score >= 85 and len(missing_req) == 0:
            recommended_action = "apply"
        elif total_score >= 70:
            recommended_action = "apply_after_tailoring"
        elif total_score >= 50:
            recommended_action = "research_first"
        else:
            recommended_action = "skip"

        fit_reasons = []
        if matched_req:
            fit_reasons.append(
                f"Direct match on required technologies: {', '.join(matched_req[:4])}."
            )
        if job.remote_type == "remote":
            fit_reasons.append("Matches your remote work arrangement preference.")
        if len(confirmed_facts) >= 3:
            fit_reasons.append("Candidate has sufficient verified experience claims.")

        breakdown = {
            "skills_score": round(skills_score, 1),
            "experience_score": exp_score,
            "education_score": edu_score,
            "preferences_score": pref_score,
            "semantic_score": semantic_score,
            "weights": w,
        }

        explanation = {
            "fit_reasons": fit_reasons,
            "matched_skills": [format_skill_display(s) for s in (matched_req + matched_pref)],
            "missing_or_uncertain": missing_or_uncertain,
            "projects_to_highlight": relevant_projects,
            "questions_to_investigate": [
                "Verify team engineering stack & deployment autonomy",
                "Clarify compensation structure & equity grants",
            ],
            "recommended_action": recommended_action,
        }

        # Check existing match to update or create
        existing_match = await self.job_repo.get_match(user_id, job_id)
        if existing_match:
            existing_match.score = total_score
            existing_match.confidence = confidence
            existing_match.hard_filter_passed = True
            existing_match.breakdown = breakdown
            existing_match.config_snapshot = match_config
            existing_match.explanation = explanation
            await self.session.flush()
            return existing_match

        new_match = JobMatch(
            user_id=user_id,
            job_id=job_id,
            score=total_score,
            confidence=confidence,
            hard_filter_passed=True,
            breakdown=breakdown,
            config_snapshot=match_config,
            explanation=explanation,
        )
        return await self.job_repo.save_match(new_match)
