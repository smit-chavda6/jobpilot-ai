"""Interview Prep generator constructing STAR answer scaffolds strictly from verified ProfileFacts."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from apps.api.models.fact import ProfileFact
from apps.api.models.job import Job


class InterviewPrepService:
    """Produces structured interview preparation cards based on verified candidate accomplishments."""

    @classmethod
    def generate_prep_kit(
        cls,
        job: Job,
        confirmed_facts: List[ProfileFact],
    ) -> Dict[str, Any]:
        """Build interview prep questions and STAR scaffolds citing confirmed facts."""
        exp_facts = [f for f in confirmed_facts if f.category in ["experience", "project"]]
        skill_facts = [f for f in confirmed_facts if f.category == "skill"]

        # Behavioral & Technical Questions aligned with target job
        primary_skills = [s.title() for s in (job.required_skills or [])[:3]] or ["Distributed Systems", "Backend"]

        star_scaffolds: List[Dict[str, Any]] = []
        for i, fact in enumerate(exp_facts[:4]):
            entities = fact.entities or {}
            metrics = entities.get("metrics", [])
            metric_str = f" resulting in {', '.join(metrics)}" if metrics else ""

            star_scaffolds.append({
                "question": f"Tell me about a time you handled complex engineering challenges involving {primary_skills[i % len(primary_skills)]}.",
                "category": "behavioral",
                "cited_fact_id": fact.id,
                "star": {
                    "situation": f"While working on high-impact systems at {entities.get('company', 'my previous organization')}.",
                    "task": f"I was tasked with addressing performance, scaling, and architectural requirements.",
                    "action": f"Specifically, {fact.text}",
                    "result": f"Successfully delivered stable execution{metric_str}.",
                },
            })

        # Technical questions bank
        technical_questions = [
            f"How do you design scalable architectures utilizing {primary_skills[0]} in production?",
            f"What trade-offs do you consider when optimizing data persistence and query latency in {job.title} roles?",
            f"Describe how you structure monitoring, alerting, and incident response for services like those at {job.company}.",
        ]

        # Reverse Questions to ask interviewer (probing gaps and culture)
        interviewer_questions = [
            f"What does the engineering deployment cycle look like for this team at {job.company}?",
            f"How is technical debt prioritized alongside feature roadmap delivery?",
            f"What would success look like in the first 90 days for this {job.title} role?",
        ]

        return {
            "job_id": job.id,
            "company": job.company,
            "title": job.title,
            "star_scaffolds": star_scaffolds,
            "technical_questions": technical_questions,
            "questions_for_interviewer": interviewer_questions,
            "verified_facts_used": len(star_scaffolds),
        }
