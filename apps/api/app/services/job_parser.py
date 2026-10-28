"""Sanitise and normalise raw job postings into `JobDraft`s (rules-based extraction)."""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from html.parser import HTMLParser
from typing import Any

import nh3

from app.services.skills import detect_education, extract_skills

ALLOWED_TAGS = {"p", "br", "ul", "ol", "li", "strong", "b", "em", "i", "h1", "h2", "h3", "h4", "a", "span", "div"}


@dataclass
class JobDraft:
    title: str
    company: str = ""
    location: str = ""
    url: str | None = None
    description_html: str = ""
    description_text: str = ""
    remote_policy: str = "unknown"
    employment_type: str = "unknown"
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str | None = None
    min_years: float | None = None
    education_req: str | None = None
    required_skills: list[str] = field(default_factory=list)
    preferred_skills: list[str] = field(default_factory=list)
    sponsorship: str = "unknown"
    contact_email: str | None = None
    posted_at: datetime | None = None
    source_ref: str | None = None
    is_demo: bool = False


def sanitize_html(raw: str) -> str:
    return nh3.clean(raw, tags=ALLOWED_TAGS, attributes={"a": {"href"}}, link_rel="noopener noreferrer nofollow")


class _TextExtractor(HTMLParser):
    BLOCK = {"p", "br", "li", "div", "h1", "h2", "h3", "h4", "tr", "ul", "ol"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style", "noscript", "template"):
            self._skip += 1
        elif tag in self.BLOCK:
            self.parts.append("\n- " if tag == "li" else "\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "noscript", "template") and self._skip:
            self._skip -= 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def html_to_text(raw: str) -> str:
    parser = _TextExtractor()
    parser.feed(raw)
    text = html.unescape("".join(parser.parts))
    text = re.sub(r"[ \t\xa0]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


_SALARY_RE = re.compile(
    r"(?P<cur>[$€£₹]|usd|eur|gbp|inr)?\s?(?P<a>\d{2,3}(?:[,.]\d{3})+|\d+(?:\.\d+)?\s?[kK]|\d+(?:\.\d+)?\s?(?:lpa|lakhs?|l))"
    r"\s*(?:-|–|to)\s*(?P<cur2>[$€£₹]|usd|eur|gbp|inr)?\s?"
    r"(?P<b>\d{2,3}(?:[,.]\d{3})+|\d+(?:\.\d+)?\s?[kK]|\d+(?:\.\d+)?\s?(?:lpa|lakhs?|l))",
    re.IGNORECASE,
)
_YEARS_RE = re.compile(
    r"(\d{1,2})\s*\+?\s*(?:-\s*\d{1,2}\s*)?(?:years?|yrs?)(?:\s+of)?(?:\s+\w+){0,4}\s+experience", re.I
)
_YEARS_RE2 = re.compile(r"(?:minimum|at least|min\.?)\s+(?:of\s+)?(\d{1,2})\s*\+?\s*(?:years?|yrs?)", re.I)
_PREFERRED_HEADING = re.compile(r"^\W*(preferred|nice[- ]to[- ]have|bonus|pluses|good to have|desired)", re.I | re.M)
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_CUR = {"$": "USD", "usd": "USD", "€": "EUR", "eur": "EUR", "£": "GBP", "gbp": "GBP", "₹": "INR", "inr": "INR"}


def _money(token: str) -> tuple[int, bool]:
    t = token.lower().replace(" ", "")
    if t.endswith(("lpa", "lakh", "lakhs", "l")):
        num = float(re.sub(r"[a-z]+$", "", t))
        return int(num * 100_000), True
    if t.endswith("k"):
        return int(float(t[:-1]) * 1000), False
    return int(re.sub(r"[,.]", "", t)), False


def parse_salary(text: str) -> tuple[int | None, int | None, str | None]:
    for m in _SALARY_RE.finditer(text):
        a, lakh_a = _money(m.group("a"))
        b, lakh_b = _money(m.group("b"))
        cur_tok = (m.group("cur") or m.group("cur2") or "").lower()
        cur = _CUR.get(cur_tok) or ("INR" if (lakh_a or lakh_b) else None)
        if b < a:
            a, b = b, a
        if b >= 1000 and (cur or b >= 10_000):
            return a, b, cur
    return None, None, None


def detect_remote(text: str, location: str = "") -> str:
    t = f"{location}\n{text}".lower()
    if re.search(r"\bhybrid\b", t):
        return "hybrid"
    if re.search(r"\b(fully remote|100% remote|remote[- ]first|work from home|remote)\b", t) and not re.search(
        r"\bnot (?:a )?remote\b|\bno remote\b", t
    ):
        return "remote"
    if re.search(r"\b(on[- ]?site|in[- ]office|onsite)\b", t):
        return "onsite"
    return "unknown"


def detect_employment_type(text: str) -> str:
    t = text.lower()
    for label, pattern in (
        ("internship", r"\bintern(ship)?\b"),
        ("contract", r"\b(contract|contractor|freelance|temporary)\b"),
        ("part_time", r"\bpart[- ]time\b"),
        ("full_time", r"\bfull[- ]time\b|\bpermanent\b"),
    ):
        if re.search(pattern, t):
            return label
    return "unknown"


def detect_sponsorship(text: str) -> str:
    t = text.lower()
    if re.search(
        r"(no|not|unable to|cannot|can't|won't|will not)\s+(provide\s+|offer\s+)?(visa\s+)?sponsor", t
    ) or re.search(r"must be (legally )?authori[sz]ed to work .* without sponsorship", t):
        return "not_offered"
    if re.search(r"(visa )?sponsorship (is )?(available|provided|offered)|we sponsor visas|will sponsor", t):
        return "offered"
    return "unknown"


def detect_min_years(text: str) -> float | None:
    vals = [int(m.group(1)) for m in _YEARS_RE.finditer(text)] + [int(m.group(1)) for m in _YEARS_RE2.finditer(text)]
    vals = [v for v in vals if 0 < v <= 30]
    return float(min(vals)) if vals else None


def split_skills(text: str) -> tuple[list[str], list[str]]:
    m = _PREFERRED_HEADING.search(text)
    if m:
        required_part, preferred_part = text[: m.start()], text[m.start() :]
    else:
        required_part, preferred_part = text, ""
    required = extract_skills(required_part)
    preferred = [s for s in extract_skills(preferred_part) if s not in required]
    return required, preferred


def enrich(draft: JobDraft) -> JobDraft:
    """Fill structured fields from the plain-text description where not already provided."""
    text = draft.description_text
    if draft.remote_policy == "unknown":
        draft.remote_policy = detect_remote(text, draft.location)
    if draft.employment_type == "unknown":
        draft.employment_type = detect_employment_type(f"{draft.title}\n{text}")
    if draft.salary_min is None and draft.salary_max is None:
        draft.salary_min, draft.salary_max, draft.salary_currency = parse_salary(text)
    if draft.min_years is None:
        draft.min_years = detect_min_years(text)
    if draft.education_req is None:
        draft.education_req = detect_education(text)
    if not draft.required_skills and not draft.preferred_skills:
        draft.required_skills, draft.preferred_skills = split_skills(f"{draft.title}\n{text}")
    if draft.sponsorship == "unknown":
        draft.sponsorship = detect_sponsorship(text)
    if draft.contact_email is None and (m := _EMAIL_RE.search(text)):
        draft.contact_email = m.group(0).lower()
    draft.title = draft.title.strip()[:300] or "Untitled role"
    draft.company = draft.company.strip()[:200]
    draft.location = draft.location.strip()[:200]
    return draft


def from_html(raw_html: str, **fields: Any) -> JobDraft:
    clean = sanitize_html(raw_html)
    return enrich(JobDraft(description_html=clean, description_text=html_to_text(clean), **fields))


def from_text(text: str, **fields: Any) -> JobDraft:
    safe = html.escape(text)
    return enrich(
        JobDraft(description_html=f"<p>{safe.replace(chr(10), '<br>')}</p>", description_text=text.strip(), **fields)
    )


def parse_pasted(text: str, url: str | None = None) -> JobDraft:
    """Best-effort extraction of title/company/location from a pasted posting."""
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    title = company = location = ""
    for ln in lines[:12]:
        low = ln.lower()
        if not title and (m := re.match(r"^(?:job\s+)?title\s*[:\-]\s*(.+)$", ln, re.I)):
            title = m.group(1)
        elif not company and (m := re.match(r"^(?:company|employer|organi[sz]ation)\s*[:\-]\s*(.+)$", ln, re.I)):
            company = m.group(1)
        elif not location and (m := re.match(r"^(?:location|based in|office)\s*[:\-]\s*(.+)$", ln, re.I)):
            location = m.group(1)
        elif not location and low in {"remote", "hybrid"}:
            location = ln
    if not title and lines:
        first = lines[0]
        if m := re.match(r"^(.+?)\s+(?:at|@|-|–|—|\|)\s+(.+?)(?:\s+[-–—|]\s+(.+))?$", first):
            title, company = title or m.group(1), company or m.group(2)
            location = location or (m.group(3) or "")
        else:
            title = first
    return from_text(text, title=title[:300], company=company, location=location, url=url)


def from_json_ld(page_html: str, url: str) -> JobDraft | None:
    """Extract a schema.org JobPosting (the structured data job sites publish for search engines)."""
    for block in re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', page_html, re.S | re.I
    ):
        try:
            data = json.loads(block.strip())
        except json.JSONDecodeError:
            continue
        candidates = data if isinstance(data, list) else data.get("@graph", [data]) if isinstance(data, dict) else []
        for item in candidates:
            if not isinstance(item, dict) or "JobPosting" not in str(item.get("@type", "")):
                continue
            org = item.get("hiringOrganization") or {}
            loc = item.get("jobLocation") or {}
            if isinstance(loc, list):
                loc = loc[0] if loc else {}
            addr = loc.get("address", {}) if isinstance(loc, dict) else {}
            location = ", ".join(
                str(addr.get(k))
                for k in ("addressLocality", "addressRegion", "addressCountry")
                if isinstance(addr, dict) and addr.get(k)
            )
            remote = "remote" if str(item.get("jobLocationType", "")).upper() == "TELECOMMUTE" else "unknown"
            salary = item.get("baseSalary") or {}
            value = salary.get("value", {}) if isinstance(salary, dict) else {}
            draft = from_html(
                str(item.get("description", "")),
                title=str(item.get("title", ""))[:300],
                company=str(org.get("name", "") if isinstance(org, dict) else org),
                location=location,
                url=url,
                remote_policy=remote,
            )
            if isinstance(value, dict) and value.get("minValue"):
                draft.salary_min = int(float(value["minValue"]))
                draft.salary_max = int(float(value.get("maxValue") or value["minValue"]))
                draft.salary_currency = salary.get("currency")
            return draft
    return None
