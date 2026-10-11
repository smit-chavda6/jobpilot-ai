"""Inbound email triage service parsing .eml messages and classifying job search intents."""

from __future__ import annotations

import email
from email import policy
import re
from typing import Any, Dict, List, Optional, Tuple


INTENT_KEYWORDS: Dict[str, List[str]] = {
    "interview_invite": [
        "interview", "schedule a call", "invitation to interview", "speak with the team",
        "chat with", "calendly", "phone screen", "video call", "availability for a call",
        "next round", "zoom link", "google meet", "hiring manager",
    ],
    "rejection": [
        "not moving forward", "other candidates", "unfortunately", "regret to inform",
        "decided to pursue", "high volume of applicants", "not selected",
        "wish you the best in your job search", "after careful consideration",
    ],
    "offer": [
        "offer letter", "pleased to offer", "job offer", "congratulations",
        "formal offer", "compensation package", "welcome to the team",
    ],
    "assessment_request": [
        "coding challenge", "take-home", "hackerrank", "codesignal", "technical assessment",
        "online assessment", "complete the test", "assessment link", "work sample",
    ],
    "status_update": [
        "application received", "received your application", "under review",
        "reviewing applications", "confirming receipt", "status update",
    ],
}


class EmailTriageService:
    """Parses .eml MIME emails and classifies candidate intent with suggested tracker transitions."""

    @staticmethod
    def parse_eml_content(raw_eml_bytes: bytes) -> Dict[str, Any]:
        """Extract clean headers and body from raw .eml bytes."""
        msg = email.message_from_bytes(raw_eml_bytes, policy=policy.default)

        subject = str(msg.get("subject", "") or "")
        sender = str(msg.get("from", "") or "")
        date = str(msg.get("date", "") or "")

        body_text = ""
        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                if ctype == "text/plain":
                    body_text += part.get_content() or ""
                elif ctype == "text/html" and not body_text:
                    # Strip basic HTML tags
                    raw_html = part.get_content() or ""
                    body_text += re.sub(r"<[^>]+>", " ", raw_html)
        else:
            body_text = msg.get_content() or ""

        return {
            "subject": subject.strip(),
            "sender": sender.strip(),
            "date": date.strip(),
            "body": body_text.strip(),
        }

    @classmethod
    def classify_email(cls, subject: str, body: str, sender: str = "") -> Dict[str, Any]:
        """Classify email intent and return confidence, reasoning, and suggested tracker action."""
        combined_text = f"{subject}\n{body}".lower()

        scores: Dict[str, float] = {intent: 0.0 for intent in INTENT_KEYWORDS}

        # Weight subject matches higher
        lower_sub = subject.lower()
        for intent, keywords in INTENT_KEYWORDS.items():
            for kw in keywords:
                if kw in lower_sub:
                    scores[intent] += 3.0
                if kw in combined_text:
                    scores[intent] += 1.0

        best_intent = max(scores, key=scores.get)
        max_score = scores[best_intent]

        # Extract potential company name from sender or subject
        company_guess = None
        if "at " in lower_sub:
            parts = lower_sub.split("at ")
            company_guess = parts[-1].split("-")[0].split(":")[0].strip().title()
        elif "@" in sender:
            domain = sender.split("@")[-1].split(">")[0].strip()
            parts = domain.split(".")
            if len(parts) >= 2:
                company_guess = parts[0].title()

        if max_score == 0:
            best_intent = "marketing_or_other"
            confidence = 0.50
        else:
            confidence = min(0.98, max(0.60, round(0.50 + (max_score * 0.10), 2)))

        # Map intent to suggested tracker status
        status_map = {
            "interview_invite": "interviewing",
            "rejection": "rejected",
            "offer": "offer",
            "assessment_request": "interviewing",
            "status_update": "submitted_confirmed",
            "marketing_or_other": None,
        }

        return {
            "intent": best_intent,
            "confidence": confidence,
            "suggested_status": status_map.get(best_intent),
            "extracted_company": company_guess,
            "requires_human_confirmation": True,
            "rationale": f"Classified as '{best_intent}' with confidence {confidence} based on matched keywords.",
        }
