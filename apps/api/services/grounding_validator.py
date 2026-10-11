"""Deterministic Grounding Validator for Resume & Cover Letter generation.

Disallows any claim that cannot cite a confirmed ProfileFact ID.
Flags invented metrics, unlisted employers, unlisted degrees, and unsupported technologies.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from apps.api.models.fact import ProfileFact

# Known common tech terms to guard against hallucinations
KNOWN_TECH_TOKENS = {
    "python", "javascript", "typescript", "golang", "go", "rust", "java", "c++", "c#",
    "react", "vue", "angular", "next.js", "node.js", "django", "fastapi", "flask",
    "postgresql", "mysql", "mongodb", "redis", "dynamodb", "cassandra",
    "aws", "azure", "gcp", "docker", "kubernetes", "terraform", "ansible",
    "graphql", "rest", "grpc", "kafka", "rabbitmq", "celery", "elasticsearch",
    "pytorch", "tensorflow", "scikit-learn", "huggingface", "llm", "langchain",
    "spark", "hadoop", "snowflake", "bigquery", "airflow",
}

# Known degrees and education credentials
KNOWN_DEGREE_TOKENS = {
    "phd", "ph.d", "doctorate", "master", "masters", "m.s.", "m.s", "ms",
    "mba", "bachelor", "bachelors", "b.s.", "b.s", "bs", "b.a.", "b.a", "ba",
}


@dataclass
class GroundingResult:
    is_grounded: bool
    grounding_score: float
    violations: List[str] = field(default_factory=list)
    cited_fact_ids: List[str] = field(default_factory=list)
    total_claims: int = 0
    grounded_claims: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_grounded": self.is_grounded,
            "grounding_score": round(self.grounding_score, 2),
            "violations": self.violations,
            "cited_fact_ids": self.cited_fact_ids,
            "total_claims": self.total_claims,
            "grounded_claims": self.grounded_claims,
        }


class GroundingValidator:
    """Validates claims against a user's verified ProfileFact set."""

    def __init__(self, confirmed_facts: List[ProfileFact]):
        # Strictly filter to only confirmed facts
        self.confirmed_facts_map: Dict[str, ProfileFact] = {
            f.id: f for f in confirmed_facts if f.confirmation_status == "confirmed"
        }
        self.confirmed_fact_ids: Set[str] = set(self.confirmed_facts_map.keys())

        # Build corpus of confirmed entities
        self.confirmed_skills: Set[str] = set()
        self.confirmed_employers: Set[str] = set()
        self.confirmed_degrees: Set[str] = set()
        self.confirmed_texts: List[str] = []

        for fact in self.confirmed_facts_map.values():
            self.confirmed_texts.append(fact.text.lower())
            entities = fact.entities or {}

            # Skills
            if fact.category == "skill":
                self.confirmed_skills.add(fact.text.lower().strip())
            for sk in entities.get("skills", []):
                self.confirmed_skills.add(str(sk).lower().strip())

            # Employers / Experience
            if fact.category == "experience":
                if "company" in entities:
                    self.confirmed_employers.add(str(entities["company"]).lower().strip())
                if "employer" in entities:
                    self.confirmed_employers.add(str(entities["employer"]).lower().strip())

            # Education
            if fact.category == "education":
                if "degree" in entities:
                    self.confirmed_degrees.add(str(entities["degree"]).lower().strip())
                if "institution" in entities:
                    self.confirmed_employers.add(str(entities["institution"]).lower().strip())

    @staticmethod
    def extract_metrics(text: str) -> List[str]:
        """Extract percentages, currency, multipliers, and numbers with magnitude."""
        patterns = [
            r"\b\d+(?:\.\d+)?%\b",                    # 15%, 99.9%
            r"\$\d+(?:,\d+)*(?:\.\d+)?[kmbKMB]?\b",   # $100k, $1.5M, $500
            r"\b\d+(?:\.\d+)?x\b",                    # 2x, 10x
            r"\b\d{2,}\+?\b",                         # 10+, 500, 1000
        ]
        found: List[str] = []
        for p in patterns:
            found.extend(re.findall(p, text))
        return list(dict.fromkeys(found))

    def validate_claim(
        self,
        claim_text: str,
        cited_fact_ids: Optional[List[str]] = None,
    ) -> List[str]:
        """Validate an individual claim against its cited facts."""
        violations: List[str] = []

        if not claim_text.strip():
            return violations

        # 1. Fact Citation Check
        if not cited_fact_ids:
            violations.append(f"Missing citation: Claim '{claim_text[:60]}...' does not cite any fact_id.")
            return violations

        for fid in cited_fact_ids:
            if fid not in self.confirmed_fact_ids:
                violations.append(
                    f"Unconfirmed or invalid citation: Fact '{fid}' is not in the candidate's confirmed facts."
                )

        if violations:
            return violations

        # Gather supporting text and entities from cited facts
        supporting_facts = [self.confirmed_facts_map[fid] for fid in cited_fact_ids]
        supporting_text = " ".join([f.text.lower() for f in supporting_facts])

        # 2. Metric / Quantifier Check
        claim_metrics = self.extract_metrics(claim_text)
        for metric in claim_metrics:
            norm_metric = metric.lower()
            if norm_metric not in supporting_text:
                # Also check digit match
                digits = re.findall(r"\d+", metric)
                if not any(d in supporting_text for d in digits):
                    violations.append(
                        f"Invented metric: '{metric}' in claim '{claim_text[:50]}...' is not grounded in cited facts."
                    )

        # 3. Unsupported Technology Check
        lower_claim = claim_text.lower()
        for tech in KNOWN_TECH_TOKENS:
            # Check whole word match
            if re.search(rf"\b{re.escape(tech)}\b", lower_claim):
                # Must be supported either in cited facts or confirmed skills
                tech_supported = (
                    tech in supporting_text
                    or tech in self.confirmed_skills
                    or any(tech in f.text.lower() for f in supporting_facts)
                )
                if not tech_supported:
                    violations.append(
                        f"Unsupported technology: '{tech}' claimed but not present in confirmed profile facts."
                    )

        # 4. Unlisted Degree Check
        for deg in KNOWN_DEGREE_TOKENS:
            if re.search(rf"\b{re.escape(deg)}\b", lower_claim):
                deg_supported = any(
                    deg in d for d in self.confirmed_degrees
                ) or deg in supporting_text
                if not deg_supported:
                    violations.append(
                        f"Unlisted degree or credential: '{deg}' claimed without confirmed education facts."
                    )

        return violations

    def validate_content(
        self,
        claims: List[Dict[str, Any]],
    ) -> GroundingResult:
        """Validate a list of claims: [{'text': '...', 'cited_fact_ids': ['...']}]."""
        all_violations: List[str] = []
        all_cited: List[str] = []
        grounded_count = 0

        for claim in claims:
            text = claim.get("text", "")
            cites = claim.get("cited_fact_ids", [])
            all_cited.extend(cites)

            v = self.validate_claim(text, cites)
            if v:
                all_violations.extend(v)
            else:
                grounded_count += 1

        total = len(claims)
        score = (grounded_count / total) if total > 0 else 1.0
        is_grounded = len(all_violations) == 0

        return GroundingResult(
            is_grounded=is_grounded,
            grounding_score=score,
            violations=all_violations,
            cited_fact_ids=list(dict.fromkeys(all_cited)),
            total_claims=total,
            grounded_claims=grounded_count,
        )
