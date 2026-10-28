"""Grounding validator (spec §6) - deterministic checks; an optional LLM checker may only ADD failures.

For every generated item:
 1. reject if it cites no supporting fact ids (claims) or cites unknown/unconfirmed facts;
 2. entities in the output (numbers, dates, tools/skills, proper nouns, degrees) must be a subset of
    the entities in the cited facts;
 3. flag inflated scope/proficiency words ("led", "expert", ...) not present in the cited facts;
 4. failing items are blocked from export and reported with reasons.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.services.skills import extract_skills, normalize_skill

INFLATION_WORDS = {
    "led",
    "lead",
    "leading",
    "spearheaded",
    "headed",
    "managed",
    "directed",
    "architected",
    "owned",
    "expert",
    "world-class",
    "senior",
    "principal",
    "pioneered",
    "revolutionized",
    "transformed",
    "orchestrated",
    "drove",
    "mentored",
    "founded",
    "award-winning",
    "top",
    "best",
    "mastered",
    "guru",
    "ninja",
    "rockstar",
    "extensive",
    "deep",
    "advanced",
    "proficient",
}
COMMON_CAPITALIZED = {
    "i",
    "the",
    "a",
    "an",
    "in",
    "at",
    "on",
    "for",
    "with",
    "and",
    "to",
    "of",
    "my",
    "as",
    "by",
    "from",
    "dear",
    "hiring",
    "manager",
    "team",
    "sincerely",
    "regards",
    "thank",
    "you",
    "best",
    "kind",
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
    "jan",
    "feb",
    "mar",
    "apr",
    "jun",
    "jul",
    "aug",
    "sep",
    "sept",
    "oct",
    "nov",
    "dec",
    "skill",
    "skills",
    "experience",
    "projects",
    "project",
    "education",
    "summary",
    "built",
    "developed",
    "created",
    "designed",
    "implemented",
    "worked",
    "used",
    "using",
    "this",
    "that",
    "these",
    "it",
    "role",
    "position",
    "company",
    "opportunity",
    "looking",
    "forward",
    "excited",
    "interested",
}
_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*\s*(?:%|x\b|k\b|m\b|\+)?", re.I)
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9&.+#'-]*")
_DEGREE_RE = re.compile(
    r"\b(ph\.?d|doctorate|master'?s?|m\.?s\.?c?|m\.?tech|mba|bachelor'?s?|b\.?s\.?c?|b\.?tech|b\.?e|"
    r"associate'?s? degree|diploma|certified|certification|certificate)\b",
    re.I,
)
_FRAMING_CLAIM_RE = re.compile(
    r"\b(i have|i've|i am (?:an? )?(?:experienced|skilled|expert)|my experience|years of|i built|i led|"
    r"i developed|i managed|my background|i specialize)\b",
    re.I,
)


@dataclass(frozen=True)
class FactView:
    id: str
    text: str
    attributes: dict[str, Any]
    confirmed: bool

    @property
    def corpus(self) -> str:
        attr_text = " ".join(
            " ".join(str(x) for x in v) if isinstance(v, list) else str(v) for v in self.attributes.values()
        )
        return f"{self.text} {attr_text}"


@dataclass
class ItemInput:
    id: str
    text: str
    supporting_fact_ids: list[str]
    kind: str = "claim"  # claim | framing


@dataclass
class ItemResult:
    item_id: str
    passed: bool
    reasons: list[dict[str, str]] = field(default_factory=list)

    def fail(self, code: str, message: str) -> None:
        self.passed = False
        self.reasons.append({"code": code, "message": message})


def _numbers(text: str) -> set[str]:
    out = set()
    for m in _NUMBER_RE.finditer(text):
        token = re.sub(r"\s+", "", m.group(0)).lower().rstrip("+")
        digits = re.sub(r"[.,](?=\d{3}\b)", "", token)
        out.add(digits)
    return out


def _bare_numbers(text: str) -> set[str]:
    return {re.sub(r"[^\d.]", "", n) for n in _numbers(text)}


def _proper_nouns(text: str) -> set[str]:
    nouns: set[str] = set()
    for sentence in re.split(r"(?<=[.!?:;])\s+|\n+|^\s*[-•]\s*", text):
        words = _WORD_RE.findall(sentence)
        for i, w in enumerate(words):
            if i == 0 or w.lower() in COMMON_CAPITALIZED:
                continue
            if w[0].isupper() and len(w) > 1:
                nouns.add(w.lower().strip(".'"))
    return nouns


def _skills(text: str) -> set[str]:
    return {s.lower() for s in extract_skills(text)}


def _fact_skills(f: FactView) -> set[str]:
    s = _skills(f.corpus)
    for key in ("skill",):
        if f.attributes.get(key):
            s.add(normalize_skill(str(f.attributes[key])).lower())
    for t in f.attributes.get("tools", []) or []:
        s.add(normalize_skill(str(t)).lower())
    return s


def _contains_word(corpus: str, word: str) -> bool:
    return re.search(rf"(?<![A-Za-z]){re.escape(word)}(?![A-Za-z])", corpus, re.I) is not None


def check_item(item: ItemInput, facts: dict[str, FactView], allowed_framing_terms: set[str]) -> ItemResult:
    result = ItemResult(item.id, True)
    text = item.text.strip()
    if not text:
        result.fail("empty", "Item has no text")
        return result

    if item.kind == "framing":
        if _FRAMING_CLAIM_RE.search(text):
            result.fail(
                "framing_contains_claim",
                "Framing sentences cannot make claims about your background; cite facts instead",
            )
        if _bare_numbers(text) - {""}:
            result.fail("unsupported_number", "Framing sentences cannot contain numbers")
        allowed = " ".join(allowed_framing_terms).lower()
        skills = _skills(text) - _skills(allowed)
        if skills:
            result.fail(
                "unsupported_entity", f"Framing mentions skills without citing facts: {', '.join(sorted(skills))}"
            )
        extra = {n for n in _proper_nouns(text) if not _contains_word(allowed, n)} - _skills(text)
        if extra:
            result.fail("unsupported_entity", f"Unrecognised names in framing: {', '.join(sorted(extra))}")
        return result

    if not item.supporting_fact_ids:
        result.fail("no_support", "No supporting facts cited")
        return result
    cited: list[FactView] = []
    for fid in item.supporting_fact_ids:
        f = facts.get(fid)
        if f is None or not f.confirmed:
            result.fail("unverified_fact", "Cites a fact that does not exist or is not confirmed")
        else:
            cited.append(f)
    if not cited:
        return result
    corpus = " ".join(f.corpus for f in cited)

    missing_numbers = {n for n in _bare_numbers(text) if n and n not in _bare_numbers(corpus)}
    if missing_numbers:
        result.fail("unsupported_number", f"Numbers not in cited facts: {', '.join(sorted(missing_numbers))}")
    if "%" in text and "%" not in corpus and "percent" not in corpus.lower():
        result.fail("unsupported_quantifier", "Percentage not supported by cited facts")
    if re.search(r"\b\d+\s*x\b", text, re.I) and not re.search(r"\b\d+\s*x\b", corpus, re.I):
        result.fail("unsupported_quantifier", "Multiplier (e.g. '10x') not supported by cited facts")

    fact_skills: set[str] = set()
    for f in cited:
        fact_skills |= _fact_skills(f)
    extra_skills = _skills(text) - fact_skills
    if extra_skills:
        result.fail("unsupported_entity", f"Tools/skills not in cited facts: {', '.join(sorted(extra_skills))}")

    extra_nouns = {n for n in _proper_nouns(text) if not _contains_word(corpus, n)} - _skills(text)
    if extra_nouns:
        result.fail("unsupported_entity", f"Names not in cited facts: {', '.join(sorted(extra_nouns))}")

    for m in _DEGREE_RE.finditer(text):
        if not _contains_word(corpus, m.group(0).rstrip(".")):
            result.fail("unsupported_credential", f"Credential '{m.group(0)}' not in cited facts")
            break

    words = {w.lower() for w in re.findall(r"[A-Za-z-]+", text)}
    inflated = sorted(w for w in words & INFLATION_WORDS if not _contains_word(corpus, w))
    if inflated:
        result.fail("inflation", f"Scope/proficiency words not supported by facts: {', '.join(inflated)}")
    return result


def validate(
    items: list[ItemInput],
    facts: dict[str, FactView],
    allowed_framing_terms: set[str] | None = None,
) -> dict[str, Any]:
    results = [check_item(i, facts, allowed_framing_terms or set()) for i in items]
    failed = [r for r in results if not r.passed]
    return {
        "passed": not failed and bool(items),
        "checked": len(results),
        "failed": len(failed),
        "items": {r.item_id: {"passed": r.passed, "reasons": r.reasons} for r in results},
        "validator": "deterministic@1",
    }


def merge_llm_findings(report: dict[str, Any], llm_results: list[dict[str, Any]]) -> dict[str, Any]:
    """LLM-as-checker can only add failures; it can never pass an item the deterministic check failed."""
    for r in llm_results:
        entry = report["items"].get(str(r.get("item_id")))
        if entry is not None and r.get("supported") is False:
            entry["passed"] = False
            entry["reasons"].append({"code": "llm_checker", "message": str(r.get("reason", ""))[:300]})
    report["failed"] = sum(1 for e in report["items"].values() if not e["passed"])
    report["passed"] = report["failed"] == 0 and report["checked"] > 0
    return report
