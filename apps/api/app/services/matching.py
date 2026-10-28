"""Matching engine core (spec §8): deterministic hard filters, then transparent weighted scoring.

Pure functions only - no I/O - so the engine is unit/property testable and the eval harness can
run it directly. `unknown` is never treated as a match: unknown components receive a neutral-to-
penalised value and reduce `confidence`, which is reported separately from `score`.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any

from app.services.fingerprint import normalize_company, normalize_text
from app.services.skills import education_rank, family, normalize_skill

CONFIG_VERSION = "match-config@1"
DEFAULT_WEIGHTS: dict[str, float] = {
    "skills": 0.40,
    "experience": 0.20,
    "education": 0.10,
    "preferences": 0.20,
    "semantic": 0.10,
}
UNKNOWN_VALUE = 0.4
INELIGIBLE_CAP = 25.0
ADJACENT_CREDIT = 0.25
REQUIRED_W, PREFERRED_W = 1.0, 0.4


@dataclass
class ProfileInput:
    skills: set[str] = field(default_factory=set)
    years_experience: float | None = None
    education_level: str | None = None
    target_titles: list[str] = field(default_factory=list)
    preferred_locations: list[str] = field(default_factory=list)
    remote_preference: str = "any"
    employment_types: list[str] = field(default_factory=list)
    min_salary: int | None = None
    needs_sponsorship: bool | None = None
    blocked_companies: list[str] = field(default_factory=list)
    blocked_keywords: list[str] = field(default_factory=list)
    experience_filter_mode: str = "soft"
    fact_skills: dict[str, list[str]] = field(default_factory=dict)  # fact_id -> skills (project/experience)
    embedding: list[float] | None = None


@dataclass
class JobInput:
    title: str
    company: str = ""
    location: str = ""
    remote_policy: str = "unknown"
    employment_type: str = "unknown"
    salary_min: int | None = None
    salary_max: int | None = None
    min_years: float | None = None
    education_req: str | None = None
    required_skills: list[str] = field(default_factory=list)
    preferred_skills: list[str] = field(default_factory=list)
    sponsorship: str = "unknown"
    text: str = ""
    embedding: list[float] | None = None


@dataclass
class MatchConfig:
    weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    unknown_value: float = UNKNOWN_VALUE
    ineligible_cap: float = INELIGIBLE_CAP

    def snapshot(self) -> dict[str, Any]:
        return {
            "version": CONFIG_VERSION,
            "weights": self.weights,
            "unknown_value": self.unknown_value,
            "ineligible_cap": self.ineligible_cap,
            "required_weight": REQUIRED_W,
            "preferred_weight": PREFERRED_W,
            "adjacent_credit": ADJACENT_CREDIT,
        }


@dataclass
class Component:
    value: float | None  # None == unknown
    detail: str


@dataclass
class MatchResult:
    score: float
    confidence: float
    eligible: bool
    recommended_action: str
    breakdown: dict[str, Any]
    explanation: dict[str, Any]
    config_snapshot: dict[str, Any]


# ------------------------------------------------------------------ hard filters


def _tokens(s: str) -> set[str]:
    return {t for t in normalize_text(s).split() if len(t) > 1}


def _location_ok(job: JobInput, prefs: list[str]) -> bool | None:
    if not prefs or not job.location:
        return None
    loc = normalize_text(job.location)
    return any(normalize_text(p) and (normalize_text(p) in loc or loc in normalize_text(p)) for p in prefs)


def hard_filters(p: ProfileInput, j: JobInput) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    def add(name: str, passed: bool | None, reason: str) -> None:
        results.append({"name": name, "passed": passed, "reason": reason})

    blocked = {normalize_company(c) for c in p.blocked_companies if c.strip()}
    if blocked:
        hit = normalize_company(j.company) in blocked
        add("blocked_company", not hit, "Company is on your block list" if hit else "Company not blocked")
    if p.blocked_keywords:
        hay = f"{j.title}\n{j.text}".lower()
        kw = next((k for k in p.blocked_keywords if k.strip() and k.lower() in hay), None)
        add("blocked_keyword", kw is None, f"Contains blocked keyword '{kw}'" if kw else "No blocked keywords")
    if p.employment_types and j.employment_type != "unknown":
        ok = j.employment_type in p.employment_types
        add("employment_type", ok, f"Employment type is {j.employment_type.replace('_', ' ')}")
    if p.remote_preference == "remote" and j.remote_policy == "onsite":
        add("remote_policy", False, "Role is on-site but you only want remote roles")
    elif p.remote_preference == "remote" and j.remote_policy in ("remote", "hybrid"):
        add("remote_policy", True, f"Role is {j.remote_policy}")
    if j.remote_policy != "remote":
        loc_ok = _location_ok(j, p.preferred_locations)
        if loc_ok is not None and not (p.remote_preference == "remote" and j.remote_policy == "unknown"):
            add("location", loc_ok, f"Location '{j.location}' {'matches' if loc_ok else 'is outside'} your preferences")
    if p.min_salary and j.salary_max:
        ok = j.salary_max >= p.min_salary
        add("min_salary", ok, f"Listed max salary {j.salary_max:,} vs your minimum {p.min_salary:,}")
    if p.needs_sponsorship and j.sponsorship == "not_offered":
        add("work_authorization", False, "Posting states visa sponsorship is not offered")
    if p.experience_filter_mode == "hard" and j.min_years is not None and p.years_experience is not None:
        ok = p.years_experience + 1 >= j.min_years
        add("experience_bounds", ok, f"Requires {j.min_years:g}+ years; you have {p.years_experience:g}")
    return results


# ------------------------------------------------------------------ components


def skills_component(p: ProfileInput, j: JobInput) -> tuple[Component, list[str], list[str], list[str]]:
    user = {normalize_skill(s).lower() for s in p.skills}
    user_families = {family(s) for s in p.skills} - {None}
    req = [normalize_skill(s) for s in j.required_skills]
    pref = [normalize_skill(s) for s in j.preferred_skills if normalize_skill(s) not in req]
    if not req and not pref:
        return Component(None, "The posting lists no recognisable skills"), [], [], []
    matched: list[str] = []
    adjacent: list[str] = []
    missing: list[str] = []
    got = total = 0.0
    for skills, w in ((req, REQUIRED_W), (pref, PREFERRED_W)):
        for s in skills:
            total += w
            if s.lower() in user:
                got += w
                matched.append(s)
            elif family(s) is not None and family(s) in user_families and family(s) not in ("soft", "process"):
                got += w * ADJACENT_CREDIT
                adjacent.append(s)
            elif w == REQUIRED_W:
                missing.append(s)
    value = got / total if total else 0.0
    req_matched = sum(1 for s in req if s in matched)
    return (
        Component(
            value,
            f"{req_matched}/{len(req)} required and "
            f"{sum(1 for s in pref if s in matched)}/{len(pref)} preferred skills verified",
        ),
        matched,
        adjacent,
        missing,
    )


def experience_component(p: ProfileInput, j: JobInput) -> Component:
    if j.min_years is None:
        return Component(None, "Required experience not stated")
    if p.years_experience is None:
        return Component(None, "Your years of experience are not set")
    if j.min_years <= 0:
        return Component(1.0, "No minimum experience")
    v = min(1.0, p.years_experience / j.min_years)
    return Component(v, f"{p.years_experience:g} years vs {j.min_years:g}+ required")


def education_component(p: ProfileInput, j: JobInput) -> Component:
    req, have = education_rank(j.education_req), education_rank(p.education_level)
    if req is None:
        return Component(None, "No education requirement stated")
    if have is None:
        return Component(None, "Your education level is not set")
    v = 1.0 if have >= req else 0.5 if have == req - 1 else 0.0
    return Component(v, f"Requires {j.education_req}; you have {p.education_level}")


def _title_similarity(title: str, targets: list[str]) -> float:
    jt = _tokens(title)
    best = 0.0
    for t in targets:
        tt = _tokens(t)
        if tt and jt:
            best = max(best, len(jt & tt) / len(tt))
    return best


def preferences_component(p: ProfileInput, j: JobInput) -> Component:
    parts: list[tuple[str, float]] = []
    if p.target_titles:
        parts.append(("title", _title_similarity(j.title, p.target_titles)))
    if p.remote_preference != "any" and j.remote_policy != "unknown":
        rp = (
            1.0
            if j.remote_policy == p.remote_preference
            else 0.6
            if "hybrid" in (j.remote_policy, p.remote_preference)
            else 0.2
        )
        parts.append(("remote", rp))
    loc = _location_ok(j, p.preferred_locations)
    if loc is not None and j.remote_policy != "remote":
        parts.append(("location", 1.0 if loc else 0.0))
    if p.employment_types and j.employment_type != "unknown":
        parts.append(("employment_type", 1.0 if j.employment_type in p.employment_types else 0.0))
    if p.min_salary and (j.salary_max or j.salary_min):
        top = j.salary_max or j.salary_min or 0
        parts.append(("salary", 1.0 if top >= p.min_salary else max(0.0, top / p.min_salary - 0.2)))
    if not parts:
        return Component(None, "Not enough preference data to compare")
    v = sum(x for _, x in parts) / len(parts)
    return Component(v, ", ".join(f"{n} {x:.0%}" for n, x in parts))


def cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def semantic_component(p: ProfileInput, j: JobInput) -> Component:
    if p.embedding is None or j.embedding is None or len(p.embedding) != len(j.embedding):
        return Component(None, "Semantic similarity unavailable")
    c = cosine(p.embedding, j.embedding)
    v = max(0.0, min(1.0, (c - 0.05) / 0.45))
    return Component(v, f"Profile/posting similarity {c:.2f}")


# ------------------------------------------------------------------ scoring


def recommend(score: float, confidence: float, eligible: bool) -> str:
    if not eligible:
        return "skip"
    if confidence < 0.5:
        return "research_first"
    if score >= 75:
        return "apply"
    if score >= 55:
        return "apply_after_tailoring"
    if score >= 40:
        return "research_first"
    return "skip"


def score_job(p: ProfileInput, j: JobInput, config: MatchConfig | None = None) -> MatchResult:
    cfg = config or MatchConfig()
    filters = hard_filters(p, j)
    eligible = all(f["passed"] is not False for f in filters)

    skills_c, matched, adjacent, missing = skills_component(p, j)
    comps: dict[str, Component] = {
        "skills": skills_c,
        "experience": experience_component(p, j),
        "education": education_component(p, j),
        "preferences": preferences_component(p, j),
        "semantic": semantic_component(p, j),
    }
    total_w = sum(cfg.weights.values())
    raw = 0.0
    known_w = 0.0
    breakdown: dict[str, Any] = {}
    for name, comp in comps.items():
        w = cfg.weights.get(name, 0.0) / total_w
        known = comp.value is not None
        value = comp.value if comp.value is not None else cfg.unknown_value
        raw += w * value
        if known:
            known_w += w
        breakdown[name] = {
            "value": round(comp.value, 4) if comp.value is not None else None,
            "status": "known" if known else "unknown",
            "weight": round(w, 4),
            "contribution": round(100 * w * value, 2),
            "detail": comp.detail,
        }
    score = max(0.0, min(100.0, 100.0 * raw))
    if not eligible:
        score = min(score, cfg.ineligible_cap)
    score = round(score, 1)
    confidence = round(known_w, 3)
    action = recommend(score, confidence, eligible)

    fit_reasons: list[str] = []
    missing_or_uncertain: list[str] = []
    if matched:
        fit_reasons.append(f"Verified skills match: {', '.join(matched[:8])}")
    for name in ("experience", "education", "preferences"):
        c = comps[name]
        if c.value is not None and c.value >= 0.75:
            fit_reasons.append(c.detail)
        elif c.value is None:
            missing_or_uncertain.append(c.detail)
        elif c.value < 0.5:
            missing_or_uncertain.append(c.detail)
    if missing:
        missing_or_uncertain.append(f"Required skills not in your verified profile: {', '.join(missing[:8])}")
    if adjacent:
        missing_or_uncertain.append(f"Related (not identical) skills: {', '.join(adjacent[:6])}")
    for f in filters:
        if f["passed"] is False:
            missing_or_uncertain.insert(0, f"Hard filter: {f['reason']}")

    job_skills = {s.lower() for s in j.required_skills + j.preferred_skills}
    ranked = sorted(
        ((fid, len({s.lower() for s in skills} & job_skills)) for fid, skills in p.fact_skills.items()),
        key=lambda x: -x[1],
    )
    highlights = [fid for fid, n in ranked if n > 0][:3]

    questions: list[str] = []
    if j.salary_min is None and j.salary_max is None:
        questions.append("What is the salary range for this role?")
    if j.remote_policy == "unknown":
        questions.append("Is the role remote, hybrid or on-site?")
    if p.needs_sponsorship and j.sponsorship == "unknown":
        questions.append("Does the company sponsor work visas for this role?")
    if missing:
        questions.append(f"How essential are {', '.join(missing[:3])} for day-one success?")
    if j.min_years is None:
        questions.append("What level of experience is the team looking for?")

    explanation = {
        "fit_reasons": fit_reasons,
        "matched_skills": matched,
        "missing_or_uncertain": missing_or_uncertain,
        "projects_to_highlight": highlights,
        "questions_to_investigate": questions[:5],
        "recommended_action": action,
    }
    return MatchResult(
        score, confidence, eligible, action, {"components": breakdown, "filters": filters}, explanation, cfg.snapshot()
    )


def title_keywords(title: str) -> list[str]:
    return [t for t in re.findall(r"[a-z]+", title.lower()) if len(t) > 2]
