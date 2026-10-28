"""Grounding validator with known-hallucination fixtures (spec §6, §16)."""

import pytest

from app.services.grounding import FactView, ItemInput, merge_llm_findings, validate

FACTS = {
    "f1": FactView(
        "f1",
        "Built a customer churn prediction model using Python, scikit-learn and XGBoost that improved "
        "retention campaign precision by 18%.",
        {"employer": "Acme Analytics", "title": "Data Scientist", "start": "Jan 2022", "end": "Present"},
        True,
    ),
    "f2": FactView(
        "f2",
        "Automated weekly sales reporting with SQL and Pandas, saving 6 hours per week.",
        {"employer": "Northwind Retail"},
        True,
    ),
    "f3": FactView("f3", "M.Sc. Data Science, University of Hyderabad (2018 – 2020)", {}, True),
    "f4": FactView("f4", "Skill: Python", {"skill": "Python"}, True),
    "cand": FactView("cand", "Led a team of 10 engineers at Google", {}, False),
}


def run(text: str, ids: list[str], kind: str = "claim", allowed: set[str] | None = None) -> dict:  # type: ignore[type-arg]
    return validate([ItemInput("i", text, ids, kind)], FACTS, allowed)["items"]["i"]


def codes(result: dict) -> set[str]:  # type: ignore[type-arg]
    return {r["code"] for r in result["reasons"]}


def test_verbatim_fact_passes() -> None:
    assert run(FACTS["f1"].text, ["f1"])["passed"]
    assert run("Automated weekly sales reporting with SQL and Pandas.", ["f2"])["passed"]


HALLUCINATIONS = [
    ("Built a churn model using Python and TensorFlow.", ["f1"], "unsupported_entity"),  # tool not in fact
    ("Improved retention campaign precision by 45%.", ["f1"], "unsupported_number"),  # inflated number
    ("Built a churn model at Google using Python.", ["f1"], "unsupported_entity"),  # employer swap
    ("Led the churn prediction model effort using Python.", ["f1"], "inflation"),  # scope inflation
    ("Expert in Python and scikit-learn.", ["f1"], "inflation"),  # proficiency inflation
    ("Delivered a 10x speedup in sales reporting with SQL.", ["f2"], "unsupported_quantifier"),  # multiplier
    ("Ph.D. in Data Science, University of Hyderabad.", ["f3"], "unsupported_credential"),  # degree upgrade
    ("Built dashboards in Tableau.", [], "no_support"),  # no citation
    ("Led a team of 10 engineers at Google.", ["cand"], "unverified_fact"),  # unconfirmed fact
    ("Built a churn prediction model.", ["does-not-exist"], "unverified_fact"),  # unknown fact
    ("Saved 6 hours per week with SQL, cutting costs by $2 million.", ["f2"], "unsupported_number"),
]


@pytest.mark.parametrize("text,ids,code", HALLUCINATIONS)
def test_hallucination_fixtures_blocked(text: str, ids: list[str], code: str) -> None:
    result = run(text, ids)
    assert not result["passed"]
    assert code in codes(result), result["reasons"]


def test_framing_rules() -> None:
    allowed = {"Machine Learning Engineer", "Nimbus AI", "Alex Rivera"}
    assert run("I am writing to apply for the Machine Learning Engineer role at Nimbus AI.", [], "framing", allowed)[
        "passed"
    ]
    assert run("Sincerely, Alex Rivera", [], "framing", allowed)["passed"]
    assert "framing_contains_claim" in codes(
        run("I have 8 years of experience with Kubernetes.", [], "framing", allowed)
    )
    assert "unsupported_entity" in codes(run("I admire how Nimbus AI uses Rust.", [], "framing", allowed))
    assert "unsupported_entity" in codes(run("Thanks to Microsoft for referring me.", [], "framing", allowed))


def test_report_counts_and_export_gate_flag() -> None:
    report = validate([ItemInput("a", FACTS["f2"].text, ["f2"]), ItemInput("b", "Expert in SQL.", ["f2"])], FACTS)
    assert report["checked"] == 2 and report["failed"] == 1 and report["passed"] is False


def test_llm_checker_can_only_add_failures() -> None:
    report = validate([ItemInput("a", FACTS["f2"].text, ["f2"]), ItemInput("b", "Expert in SQL.", ["f2"])], FACTS)
    merged = merge_llm_findings(
        report, [{"item_id": "b", "supported": True}, {"item_id": "a", "supported": False, "reason": "overstated"}]
    )
    assert merged["items"]["b"]["passed"] is False  # LLM cannot rescue a deterministic failure
    assert merged["items"]["a"]["passed"] is False and merged["failed"] == 2
