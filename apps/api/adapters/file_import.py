"""CSV and JSON Structured File Import Adapter."""

import csv
import io
import json
from typing import List

from apps.api.adapters.base import JobDraft
from apps.api.services.resume_parser_service import extract_skills_from_text


def parse_json_jobs(content: str) -> List[JobDraft]:
    """Parses JSON content (list of job dictionaries or single job dictionary)."""
    data = json.loads(content)
    if isinstance(data, dict):
        data = [data]

    drafts = []
    for item in data:
        title = item.get("title", "Untitled Position")
        company = item.get("company", "Unknown Company")
        desc = item.get("description", "")
        skills = item.get("skills") or extract_skills_from_text(desc)

        drafts.append(
            JobDraft(
                title=title,
                company=company,
                description=desc,
                location=item.get("location", "Remote"),
                remote_type=item.get("remote_type", "remote"),
                employment_type=item.get("employment_type", "full-time"),
                salary_min=item.get("salary_min"),
                salary_max=item.get("salary_max"),
                required_skills=skills[:6] if isinstance(skills, list) else [],
                preferred_skills=skills[6:] if isinstance(skills, list) else [],
                source_id="json_import",
                source_url=item.get("url") or item.get("source_url"),
            )
        )
    return drafts


def parse_csv_jobs(content: str) -> List[JobDraft]:
    """Parses CSV content with standard column headers."""
    reader = csv.DictReader(io.StringIO(content))
    drafts = []
    for row in reader:
        title = row.get("title") or row.get("Title") or "Untitled Position"
        company = row.get("company") or row.get("Company") or "Unknown Company"
        desc = row.get("description") or row.get("Description") or ""
        skills = extract_skills_from_text(desc)

        drafts.append(
            JobDraft(
                title=title,
                company=company,
                description=desc,
                location=row.get("location") or row.get("Location") or "Remote",
                remote_type="remote"
                if "remote" in title.lower() or "remote" in desc.lower()
                else "on-site",
                employment_type="full-time",
                required_skills=skills[:5],
                preferred_skills=skills[5:8],
                source_id="csv_import",
                source_url=row.get("url") or row.get("URL"),
            )
        )
    return drafts
