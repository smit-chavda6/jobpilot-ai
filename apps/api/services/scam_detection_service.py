"""Scam & Quality Signal Engine providing transparent probabilistic risk assessments."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


class ScamDetectionService:
    """Evaluates job listings and recruiter messages for suspicious patterns without silent blocks."""

    FREE_MAIL_DOMAINS = {"gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "aol.com"}
    CHAT_APP_KEYWORDS = ["telegram", "whatsapp", "signal", "google hangouts", "wire app", "skype id"]

    @classmethod
    def evaluate_job(
        cls,
        title: str,
        company: str,
        description: str,
        contact_email: Optional[str] = None,
        salary_max: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Perform deterministic and heuristic scam signal checks."""
        flags: List[Dict[str, str]] = []
        risk_score = 0.0
        lower_desc = description.lower()
        lower_title = title.lower()

        # 1. Payment / Equipment / Check cashing requests (High Risk)
        payment_triggers = [
            "wire transfer", "send a check", "cashier's check", "buy home office equipment",
            "purchase equipment from our vendor", "send payment", "background check fee",
            "reimburse you via check", "crypto wallet", "bitcoin payment",
        ]
        for trigger in payment_triggers:
            if trigger in lower_desc:
                flags.append({
                    "signal": "PAYMENT_OR_CHECK_REQUEST",
                    "severity": "HIGH",
                    "evidence": f"Found mention of '{trigger}'. Legitimate employers never ask candidates to send money or purchase equipment upfront.",
                })
                risk_score += 0.45
                break

        # 2. Suspicious communication channels (High Risk)
        for app in cls.CHAT_APP_KEYWORDS:
            if app in lower_desc:
                flags.append({
                    "signal": "SUSPICIOUS_COMMUNICATION_CHANNEL",
                    "severity": "HIGH",
                    "evidence": f"Found request to interview via '{app}'. Scammers frequently route victims away from corporate communication tools.",
                })
                risk_score += 0.35
                break

        # 3. Free webmail domain representing enterprise company (Medium Risk)
        if contact_email and "@" in contact_email:
            domain = contact_email.split("@")[-1].lower().strip()
            if domain in cls.FREE_MAIL_DOMAINS and len(company) > 3:
                flags.append({
                    "signal": "FREE_MAIL_DOMAIN",
                    "severity": "MEDIUM",
                    "evidence": f"Recruiter contact domain is '{domain}' instead of an official corporate domain for '{company}'.",
                })
                risk_score += 0.25

        # 4. Wildly above-market entry compensation (Medium Risk)
        if salary_max and salary_max >= 250000:
            if any(term in lower_title for term in ["entry level", "junior", "data entry", "assistant", "receptionist"]):
                flags.append({
                    "signal": "UNREALISTIC_SALARY",
                    "severity": "HIGH",
                    "evidence": f"Reported maximum salary ${salary_max:,} is statistically an outlier for an entry-level or assistant title.",
                })
                risk_score += 0.35

        # 5. Overly vague / short description (Low Risk)
        if len(description.strip()) < 120:
            flags.append({
                "signal": "EXTREMELY_SHORT_JD",
                "severity": "LOW",
                "evidence": f"Job description is only {len(description.strip())} characters, omitting role duties or requirements.",
            })
            risk_score += 0.15

        # 6. Urgent or pressure tactics (Low/Medium Risk)
        urgent_triggers = ["act immediately", "immediate hire without interview", "no experience needed guaranteed hire"]
        for ut in urgent_triggers:
            if ut in lower_desc:
                flags.append({
                    "signal": "PRESSURE_TACTIC",
                    "severity": "MEDIUM",
                    "evidence": f"Found phrase '{ut}'. High-pressure or zero-interview hiring guarantees are common scam tactics.",
                })
                risk_score += 0.20
                break

        # Cap risk score between 0.0 and 1.0
        final_risk = min(1.0, round(risk_score, 2))

        if final_risk >= 0.60:
            risk_level = "high"
        elif final_risk >= 0.30:
            risk_level = "medium"
        else:
            risk_level = "low"

        return {
            "risk_score": final_risk,
            "risk_level": risk_level,
            "is_suspicious": final_risk >= 0.40,
            "signal_count": len(flags),
            "flags": flags,
            "recommendation": (
                "Proceed with caution: verify the recruiter's identity on LinkedIn and inspect company domain before replying."
                if final_risk >= 0.40
                else "No high-risk scam indicators detected."
            ),
        }
