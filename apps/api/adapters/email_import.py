"""Uploaded MIME Email (.eml) Job Alert Adapter."""

import email
import re
from email import policy
from typing import List

from bs4 import BeautifulSoup

from apps.api.adapters.base import JobDraft
from apps.api.services.resume_parser_service import extract_skills_from_text


def parse_eml_job_alert(eml_bytes: bytes) -> List[JobDraft]:
    """Parses .eml MIME job alert emails without requiring live OAuth access."""
    msg = email.message_from_bytes(eml_bytes, policy=policy.default)
    subject = msg.get("Subject", "Job Alert")

    body_text = ""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == "text/plain":
                body_text += part.get_content() + "\n"
            elif ctype == "text/html":
                soup = BeautifulSoup(part.get_content(), "html.parser")
                body_text += soup.get_text(separator="\n") + "\n"
    else:
        content = msg.get_content()
        if isinstance(content, str):
            body_text = content

    # Extract job information from subject and body
    # Standard format: e.g., "New Job: Software Engineer at Stripe" or general alert
    company_match = re.search(r"at\s+([A-Z][A-Za-z0-9\s]+)", subject)
    company = company_match.group(1).strip() if company_match else "Alert Employer"

    title = subject
    if "at " in subject:
        title = subject.split("at ")[0].replace("New Job:", "").replace("Job Alert:", "").strip()

    skills = extract_skills_from_text(body_text)

    draft = JobDraft(
        title=title or "Software Engineer",
        company=company,
        description=body_text.strip() or f"Listing imported from job alert: {subject}",
        location="Remote",
        remote_type="remote",
        employment_type="full-time",
        required_skills=skills[:6],
        preferred_skills=skills[6:10],
        source_id="email_alert",
        source_url=None,
    )
    return [draft]
