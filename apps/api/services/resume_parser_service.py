"""Resume text extraction, parsing, and atomic ProfileFact decomposition."""

import re
from typing import Any, Dict, List, Tuple

from pypdf import PdfReader


def extract_raw_text(file_path: str, mime_type: str) -> str:
    """Extracts raw string text from PDF, DOCX, or text resume files."""
    if mime_type == "application/pdf":
        reader = PdfReader(file_path)
        pages_text = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(pages_text)

    elif "wordprocessingml" in mime_type:
        import docx

        doc = docx.Document(file_path)
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n".join(paragraphs)

    else:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()


def extract_skills_from_text(text: str) -> List[str]:
    """Extracts identified technology skills based on standard skill ontology."""
    common_skills = [
        "Python",
        "FastAPI",
        "Django",
        "Flask",
        "PostgreSQL",
        "MySQL",
        "Redis",
        "Docker",
        "Kubernetes",
        "AWS",
        "GCP",
        "Azure",
        "TypeScript",
        "JavaScript",
        "React",
        "Next.js",
        "Node.js",
        "GraphQL",
        "REST",
        "Git",
        "CI/CD",
        "PyTorch",
        "TensorFlow",
        "Pandas",
        "NumPy",
        "Scikit-Learn",
        "Kafka",
        "Celery",
        "Elasticsearch",
        "Linux",
        "SQL",
        "Tailwind",
    ]
    found = []
    text_lower = text.lower()
    for skill in common_skills:
        pattern = r"\b" + re.escape(skill.lower()) + r"\b"
        if re.search(pattern, text_lower):
            found.append(skill)
    return found


def decompose_text_into_candidate_facts(raw_text: str) -> List[Dict[str, Any]]:
    """
    Decomposes resume content into atomic claims with candidate confirmation status.
    Each candidate fact represents an atomic verifiable achievement or credential.
    """
    lines = [line.strip() for line in raw_text.split("\n") if line.strip()]
    candidate_facts: List[Dict[str, Any]] = []

    # Heuristic bullet and sentence segmentation
    bullet_prefixes = ("-", "*", "•", "–", "—", ">")

    for line in lines:
        cleaned = line.lstrip("".join(bullet_prefixes)).strip()
        # Bullet achievement or substantial sentence
        if (line.startswith(bullet_prefixes) or len(cleaned) > 40) and len(cleaned) < 300:
            category = "experience"
            if any(
                term in cleaned.lower()
                for term in ["degree", "bachelor", "master", "university", "gpa", "b.s.", "m.s."]
            ):
                category = "education"
            elif any(
                term in cleaned.lower()
                for term in ["built", "designed", "created", "open-source", "github"]
            ):
                category = "project"

            # Extract recognized entities
            entities = {
                "skills": extract_skills_from_text(cleaned),
                "metrics": re.findall(r"\b\d+[%xXkKMbB]?\b", cleaned),
            }

            candidate_facts.append(
                {
                    "text": cleaned,
                    "category": category,
                    "confirmation_status": "candidate",
                    "source_type": "resume",
                    "entities": entities,
                }
            )

    # Ensure at least one summary fact if bullet segmentation found few items
    if not candidate_facts and len(raw_text.strip()) > 20:
        first_paragraph = " ".join(lines[:3])[:250]
        candidate_facts.append(
            {
                "text": first_paragraph,
                "category": "experience",
                "confirmation_status": "candidate",
                "source_type": "resume",
                "entities": {"skills": extract_skills_from_text(first_paragraph)},
            }
        )

    return candidate_facts


def parse_resume(
    file_path: str, mime_type: str
) -> Tuple[str, Dict[str, Any], List[Dict[str, Any]]]:
    """
    Complete parsing pipeline:
    1. Extracts raw text safely.
    2. Identifies skills and metadata.
    3. Decomposes into candidate ProfileFacts.
    """
    raw_text = extract_raw_text(file_path, mime_type)
    skills = extract_skills_from_text(raw_text)
    candidate_facts = decompose_text_into_candidate_facts(raw_text)

    parsed_data = {
        "skills": skills,
        "candidate_fact_count": len(candidate_facts),
        "char_count": len(raw_text),
    }

    return raw_text, parsed_data, candidate_facts
