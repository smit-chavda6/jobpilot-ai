from app.services.match_service import Explanation
from app.services.matching import JobInput, MatchConfig, ProfileInput, score_job
from tests.conftest import FIXTURES, Api, onboard

FULL = ProfileInput(
    skills={"Python", "SQL", "scikit-learn", "Docker", "AWS"},
    years_experience=4,
    education_level="master",
    target_titles=["Machine Learning Engineer"],
    preferred_locations=["Bengaluru"],
    remote_preference="hybrid",
    employment_types=["full_time"],
    min_salary=2_000_000,
    fact_skills={"f1": ["Python", "scikit-learn"]},
)
JOB = JobInput(
    title="Machine Learning Engineer",
    company="Nimbus",
    location="Bengaluru, India",
    remote_policy="hybrid",
    employment_type="full_time",
    salary_min=2_500_000,
    salary_max=4_000_000,
    min_years=3,
    education_req="bachelor",
    required_skills=["Python", "SQL", "scikit-learn", "Docker"],
    preferred_skills=["Kubernetes"],
)


def test_strong_match_recommends_apply() -> None:
    r = score_job(FULL, JOB)
    assert r.eligible and r.score >= 75 and r.recommended_action == "apply"
    assert r.explanation["projects_to_highlight"] == ["f1"]
    Explanation.model_validate(r.explanation)
    assert r.config_snapshot["version"] == "match-config@1"


def test_unknown_is_not_a_match() -> None:
    sparse = JobInput(title="Machine Learning Engineer", required_skills=["Python"])
    r = score_job(FULL, sparse)
    comps = r.breakdown["components"]
    assert comps["experience"]["status"] == "unknown" and comps["education"]["status"] == "unknown"
    # unknown components contribute the penalised neutral value, not full credit
    assert comps["experience"]["contribution"] == round(100 * comps["experience"]["weight"] * 0.4, 2)
    assert r.confidence < score_job(FULL, JOB).confidence
    assert any("not stated" in m for m in r.explanation["missing_or_uncertain"])


def test_low_confidence_means_research_first() -> None:
    r = score_job(ProfileInput(), JobInput(title="Engineer"))
    assert r.confidence < 0.5 and r.recommended_action == "research_first"


def test_hard_filters_make_ineligible_and_cap_score() -> None:
    cases = [
        ProfileInput(**{**FULL.__dict__, "blocked_companies": ["Nimbus"]}),
        ProfileInput(**{**FULL.__dict__, "employment_types": ["contract"]}),
        ProfileInput(**{**FULL.__dict__, "remote_preference": "remote"}),
        ProfileInput(**{**FULL.__dict__, "min_salary": 9_000_000}),
        ProfileInput(**{**FULL.__dict__, "blocked_keywords": ["machine learning"]}),
        ProfileInput(**{**FULL.__dict__, "experience_filter_mode": "hard", "years_experience": 1}),
    ]
    for p in cases:
        r = score_job(p, JobInput(**{**JOB.__dict__, "remote_policy": "onsite"}))
        assert not r.eligible and r.score <= MatchConfig().ineligible_cap and r.recommended_action == "skip"
        assert r.explanation["missing_or_uncertain"][0].startswith("Hard filter")


def test_sponsorship_filter() -> None:
    p = ProfileInput(**{**FULL.__dict__, "needs_sponsorship": True})
    assert not score_job(p, JobInput(**{**JOB.__dict__, "sponsorship": "not_offered"})).eligible
    r = score_job(p, JOB)
    assert r.eligible and any("sponsor" in q for q in r.explanation["questions_to_investigate"])


def test_semantic_cannot_rescue_ineligible() -> None:
    p = ProfileInput(**{**FULL.__dict__, "blocked_companies": ["Nimbus"], "embedding": [1.0, 0.0]})
    r = score_job(p, JobInput(**{**JOB.__dict__, "embedding": [1.0, 0.0]}))
    assert r.score <= MatchConfig().ineligible_cap


def test_skill_aliases_and_adjacent() -> None:
    p = ProfileInput(skills={"JavaScript", "TensorFlow"})
    r = score_job(p, JobInput(title="x", required_skills=["JS", "PyTorch"]))
    assert "JavaScript" in r.explanation["matched_skills"]
    assert any("PyTorch" in m and "Related" in m for m in r.explanation["missing_or_uncertain"])


async def test_matches_persist_with_config_snapshot_and_rescore(api: Api) -> None:
    await onboard(api)
    r = await api.post("/api/jobs/import/manual_paste", {"text": (FIXTURES / "job_ml_engineer.txt").read_text("utf-8")})
    job_id = r.json()["created"][0]["id"]
    d = (await api.get(f"/api/jobs/{job_id}")).json()
    md = d["match_detail"]
    assert md["config_snapshot"]["weights"]["skills"] == 0.4
    assert {"Python", "SQL", "scikit-learn", "Docker", "AWS"} <= set(md["explanation"]["matched_skills"])
    assert d["match"]["eligible"] and d["match"]["score"] >= 60
    assert md["highlight_facts"] and md["highlight_facts"][0]["text"]
    # Profile change triggers a re-score (outbox -> inline worker)
    await api.patch("/api/profile", {"blocked_companies": ["Nimbus AI"]})
    d2 = (await api.get(f"/api/jobs/{job_id}")).json()
    assert d2["match"]["eligible"] is False
    assert (await api.post("/api/matches/rescore")).json()["scored"] == 1


def test_eval_harness_meets_baseline() -> None:
    import json
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[3] / "evals" / "matching"
    sys.path.insert(0, str(root))
    import runner  # type: ignore[import-not-found]

    metrics = runner.evaluate(root / "dataset.json")
    baseline = json.loads((root / "baseline.json").read_text())
    tol = baseline["tolerance"]
    assert metrics["pairs"] >= 50
    for key in ("precision_at_5", "ndcg_at_10", "spearman"):
        assert metrics[key] >= baseline[key] - tol, (key, metrics[key], baseline[key])
