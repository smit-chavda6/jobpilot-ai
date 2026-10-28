"""Rule-based scam / quality signals (spec §13).

Language is deliberately probabilistic: the engine reports *signals commonly associated with*
recruitment scams. It never states that a company or person is fraudulent.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from app.services.fingerprint import normalize_company

FREE_MAIL = {
    "gmail.com",
    "yahoo.com",
    "outlook.com",
    "hotmail.com",
    "aol.com",
    "proton.me",
    "protonmail.com",
    "icloud.com",
    "yandex.com",
    "mail.com",
    "gmx.com",
    "rediffmail.com",
    "zoho.com",
}
SEVERITY_WEIGHT = {"high": 0.45, "medium": 0.25, "low": 0.1}


@dataclass
class Signal:
    code: str
    severity: str
    message: str
    evidence: str


_RULES: list[tuple[str, str, re.Pattern[str], str]] = [
    (
        "upfront_fee",
        "high",
        re.compile(
            r"(registration|training|processing|onboarding|security|application)\s+(fee|deposit|charges?)|"
            r"pay\s+(a\s+)?(fee|deposit)|refundable deposit|purchase (your own )?(equipment|starter kit)",
            re.I,
        ),
        "Asks the candidate to pay a fee or deposit",
    ),
    (
        "off_platform_chat",
        "medium",
        re.compile(r"\b(telegram|whatsapp|signal app|wechat|google hangouts)\b", re.I),
        "Moves the conversation to a chat app instead of company channels",
    ),
    (
        "sensitive_ids",
        "high",
        re.compile(
            r"(bank account (number|details)|routing number|social security|\bssn\b|aadhaar|\bpan card\b|"
            r"passport (copy|scan)|credit card|debit card|otp)",
            re.I,
        ),
        "Requests sensitive identity or banking details early in the process",
    ),
    (
        "no_interview_offer",
        "medium",
        re.compile(
            r"(no interview (needed|required)|hired immediately|instant (hiring|offer)|"
            r"guaranteed (job|placement|income))",
            re.I,
        ),
        "Promises a job without a normal interview process",
    ),
    (
        "check_cashing",
        "high",
        re.compile(
            r"(cash (a|the) check|deposit (a|the) check|send (back )?the (difference|balance)|"
            r"gift cards?|money transfer|western union|crypto(currency)? payment)",
            re.I,
        ),
        "Mentions cheque deposits, gift cards or money transfers",
    ),
    (
        "urgency_pressure",
        "low",
        re.compile(r"(act now|limited (slots|seats)|respond within \d+ (hours|minutes)|urgent(ly)? hiring)", re.I),
        "Uses high-pressure urgency language",
    ),
]

_PAY_RE = re.compile(r"(?:\$|usd\s?)(\d[\d,]*)\s*(?:/|per)\s*(hour|hr|day|week)", re.I)


def _implausible_pay(text: str) -> Signal | None:
    for m in _PAY_RE.finditer(text):
        amount = int(m.group(1).replace(",", ""))
        unit = m.group(2).lower()
        limit = {"hour": 150, "hr": 150, "day": 600, "week": 2500}[unit]
        if amount > limit and re.search(r"no experience|entry[- ]level|from home|part[- ]time|data entry", text, re.I):
            return Signal(
                "implausible_pay", "medium", "Advertises pay that is unusually high for the described role", m.group(0)
            )
    return None


def _snippet(text: str, start: int, end: int) -> str:
    s, e = max(0, start - 40), min(len(text), end + 40)
    return ("…" if s else "") + text[s:e].replace("\n", " ").strip() + ("…" if e < len(text) else "")


def analyze(text: str, company: str = "", contact_email: str | None = None) -> dict[str, Any]:
    signals: list[Signal] = []
    for code, severity, pattern, message in _RULES:
        if m := pattern.search(text):
            signals.append(Signal(code, severity, message, _snippet(text, m.start(), m.end())))
    if pay := _implausible_pay(text):
        signals.append(pay)
    if contact_email and "@" in contact_email:
        domain = contact_email.split("@", 1)[1].lower()
        comp = normalize_company(company).replace(" ", "")
        if domain in FREE_MAIL and comp:
            signals.append(
                Signal(
                    "free_mail_recruiter",
                    "medium",
                    "Recruiter uses a free email provider while representing a company",
                    contact_email,
                )
            )
        elif comp and len(comp) >= 4 and comp[:6] not in domain.replace("-", "").replace(".", ""):
            signals.append(
                Signal(
                    "domain_mismatch",
                    "low",
                    "Contact email domain does not appear to match the company name",
                    contact_email,
                )
            )
    confidence = min(0.95, sum(SEVERITY_WEIGHT[s.severity] for s in signals))
    level = "none" if not signals else "high" if confidence >= 0.6 else "medium" if confidence >= 0.3 else "low"
    summary = (
        "No common scam signals detected. This is not a guarantee of legitimacy."
        if not signals
        else f"This posting shows {len(signals)} signal(s) commonly associated with recruitment scams. "
        "This does not mean it is fraudulent - verify the company through its official website before "
        "sharing personal information or paying anything."
    )
    return {
        "level": level,
        "confidence": round(confidence, 2),
        "summary": summary,
        "signals": [asdict(s) for s in signals],
    }
