"""Resume tailoring service producing tailored resume versions with diff view and fact provenance."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from apps.api.ai.provider import LLMProvider, MockProvider
from apps.api.models.fact import ProfileFact
from apps.api.models.job import Job
from apps.api.models.resume import Resume, ResumeVersion
from apps.api.services.grounding_validator import GroundingResult, GroundingValidator


class ResumeTailorService:
    def __init__(self, provider: Optional[LLMProvider] = None):
        self.provider = provider or MockProvider()

    def tailor_resume(
        self,
        resume: Resume,
        job: Job,
        confirmed_facts: List[ProfileFact],
        candidate_name: str = "Candidate",
        candidate_email: str = "candidate@example.com",
    ) -> Dict[str, Any]:
        """Generate tailored resume content with diffs and provenance annotations."""
        validator = GroundingValidator(confirmed_facts)

        skill_facts = [f for f in confirmed_facts if f.category == "skill"]
        exp_facts = [f for f in confirmed_facts if f.category == "experience"]
        edu_facts = [f for f in confirmed_facts if f.category == "education"]
        proj_facts = [f for f in confirmed_facts if f.category == "project"]

        # 1. Match skills with target job requirements
        job_req_skills = [s.lower().strip() for s in (job.required_skills or [])]
        matched_skills = []
        other_skills = []

        for sf in skill_facts:
            norm_s = sf.text.lower().strip()
            if any(norm_s in req or req in norm_s for req in job_req_skills):
                matched_skills.append({"name": sf.text, "fact_id": sf.id, "highlighted": True})
            else:
                other_skills.append({"name": sf.text, "fact_id": sf.id, "highlighted": False})

        prioritized_skills = matched_skills + other_skills

        # 2. Prioritize experience bullets aligning with job requirements
        tailored_bullets = []
        for ef in exp_facts:
            is_relevant = any(req in ef.text.lower() for req in job_req_skills)
            tailored_bullets.append({
                "text": ef.text,
                "fact_id": ef.id,
                "category": "experience",
                "relevance_boost": is_relevant,
                "rationale": f"Emphasizes verified experience relevant to {job.title}",
            })

        # Add project bullets
        for pf in proj_facts:
            tailored_bullets.append({
                "text": pf.text,
                "fact_id": pf.id,
                "category": "project",
                "relevance_boost": False,
                "rationale": f"Showcases verified project portfolio",
            })

        # Sort: relevant bullets first
        tailored_bullets.sort(key=lambda b: b["relevance_boost"], reverse=True)

        # 3. Tailored Summary
        top_skills_str = ", ".join([s["name"] for s in matched_skills[:3]]) or "modern software systems"
        summary_text = (
            f"Results-driven professional with deep verified background in {top_skills_str}. "
            f"Proven track record of high-impact execution aligned with {job.company}'s requirements for {job.title}."
        )
        summary_cites = [s["fact_id"] for s in matched_skills[:3]] or ([confirmed_facts[0].id] if confirmed_facts else [])

        # 4. Construct Tailored Content Object
        tailored_content = {
            "header": {
                "name": candidate_name,
                "email": candidate_email,
                "target_role": job.title,
                "target_company": job.company,
            },
            "summary": {
                "text": summary_text,
                "cited_fact_ids": summary_cites,
            },
            "skills": prioritized_skills,
            "bullets": tailored_bullets,
            "education": [
                {"text": ef.text, "fact_id": ef.id} for ef in edu_facts
            ],
        }

        # 5. Build Diff View (vs original parsed resume)
        original_skills = resume.parsed_data.get("skills", []) if resume.parsed_data else []
        diff = {
            "summary_change": {
                "before": resume.parsed_data.get("summary", "Standard software engineering summary."),
                "after": summary_text,
                "rationale": f"Focused specifically on {job.title} requirements at {job.company}.",
                "cited_fact_ids": summary_cites,
            },
            "skill_reordering": {
                "before_order": original_skills[:10],
                "after_order": [s["name"] for s in prioritized_skills[:10]],
                "highlighted_count": len(matched_skills),
                "rationale": "Prioritized required job skills to top of section for ATS scanning.",
            },
            "bullet_adjustments": [
                {
                    "fact_id": b["fact_id"],
                    "bullet": b["text"],
                    "relevance_boost": b["relevance_boost"],
                    "rationale": b["rationale"],
                }
                for b in tailored_bullets
            ],
        }

        # 6. Validate Grounding across all claims
        claims_to_validate = [
            {"text": summary_text, "cited_fact_ids": summary_cites},
        ]
        for b in tailored_bullets:
            claims_to_validate.append({"text": b["text"], "cited_fact_ids": [b["fact_id"]]})
        for s in prioritized_skills:
            claims_to_validate.append({"text": s["name"], "cited_fact_ids": [s["fact_id"]]})
        for ed in edu_facts:
            claims_to_validate.append({"text": ed.text, "cited_fact_ids": [ed.id]})

        grounding_result: GroundingResult = validator.validate_content(claims_to_validate)

        all_cited_ids = list(dict.fromkeys(
            summary_cites + [b["fact_id"] for b in tailored_bullets] + [s["fact_id"] for s in prioritized_skills]
        ))

        return {
            "target_job_id": job.id,
            "target_company": job.company,
            "target_title": job.title,
            "tailored_content": tailored_content,
            "diff": diff,
            "cited_fact_ids": all_cited_ids,
            "grounding_score": grounding_result.grounding_score,
            "is_valid": grounding_result.is_grounded,
            "violations": grounding_result.violations,
        }
