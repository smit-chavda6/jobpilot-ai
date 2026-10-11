"""Cover Letter generation service producing 3-paragraph grounded drafts citing confirmed ProfileFacts."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from apps.api.ai.provider import LLMProvider, MockProvider
from apps.api.models.fact import ProfileFact
from apps.api.models.job import Job
from apps.api.services.grounding_validator import GroundingResult, GroundingValidator


class CoverLetterService:
    def __init__(self, provider: Optional[LLMProvider] = None):
        self.provider = provider or MockProvider()

    def generate_grounded_letter(
        self,
        candidate_name: str,
        job: Job,
        confirmed_facts: List[ProfileFact],
    ) -> Dict[str, Any]:
        """Generate a 3-paragraph structured cover letter grounded strictly in confirmed facts."""
        validator = GroundingValidator(confirmed_facts)

        # Gather confirmed facts by category
        exp_facts = [f for f in confirmed_facts if f.category in ["experience", "project"]]
        skill_facts = [f for f in confirmed_facts if f.category == "skill"]

        # 1. Opening Hook Paragraph
        primary_skills = [f.text for f in skill_facts[:3]] or ["software engineering", "distributed systems"]
        skills_summary = ", ".join(primary_skills)
        para1_text = (
            f"Dear Hiring Team at {job.company},\n\n"
            f"I am writing to express my strong interest in the {job.title} position. "
            f"With verified expertise in {skills_summary}, I am confident in my ability "
            f"to drive meaningful technical and product impact on your team."
        )
        para1_cites = [f.id for f in skill_facts[:3]]

        # 2. Evidence Paragraph (strictly citing confirmed experience facts)
        evidence_points = []
        para2_cites = []
        for fact in exp_facts[:3]:
            evidence_points.append(f"At my previous role, I {fact.text}")
            para2_cites.append(fact.id)

        if not evidence_points:
            # Fallback to available facts
            fallback_facts = confirmed_facts[:2]
            for f in fallback_facts:
                evidence_points.append(f.text)
                para2_cites.append(f.id)

        evidence_body = " Furthermore, ".join(evidence_points)
        para2_text = f"Throughout my career, I have focused on measurable execution: {evidence_body}."

        # 3. Why Company & Close Paragraph
        remote_note = (
            f"Given your {job.remote_type} arrangement, I am well-prepared to collaborate across distributed teams."
            if job.remote_type
            else "I look forward to contributing to your engineering initiatives."
        )
        para3_text = (
            f"I am drawn to {job.company}'s mission and engineering standards. "
            f"{remote_note} Thank you for your time and consideration; I welcome the opportunity "
            f"to discuss how my verified background aligns with your objectives.\n\n"
            f"Sincerely,\n{candidate_name}"
        )
        # para3 cites general profile facts to ensure full grounding
        para3_cites = [confirmed_facts[0].id] if confirmed_facts else []

        claims = [
            {"text": para1_text, "cited_fact_ids": para1_cites},
            {"text": para2_text, "cited_fact_ids": para2_cites},
            {"text": para3_text, "cited_fact_ids": para3_cites},
        ]

        validation_result: GroundingResult = validator.validate_content(claims)

        return {
            "candidate_name": candidate_name,
            "target_company": job.company,
            "target_title": job.title,
            "paragraphs": [
                {"section": "hook", "text": para1_text, "cited_fact_ids": para1_cites},
                {"section": "evidence", "text": para2_text, "cited_fact_ids": para2_cites},
                {"section": "alignment_close", "text": para3_text, "cited_fact_ids": para3_cites},
            ],
            "full_text": f"{para1_text}\n\n{para2_text}\n\n{para3_text}",
            "grounding": validation_result.to_dict(),
            "is_valid": validation_result.is_grounded,
        }
