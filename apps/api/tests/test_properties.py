"""Property-based tests (Hypothesis): dedup normalisation and matching score invariants."""

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.services.fingerprint import (
    canonicalize_url,
    job_fingerprint,
    normalize_company,
    normalize_text,
    trigram_similarity,
)
from app.services.matching import JobInput, ProfileInput, score_job
from app.services.skills import ONTOLOGY

SKILLS = sorted(ONTOLOGY)
text = st.text(alphabet=st.characters(blacklist_categories=("Cs",)), max_size=60)


@given(text)
def test_normalize_is_idempotent(s: str) -> None:
    assert normalize_text(normalize_text(s)) == normalize_text(s)


@given(text, text, text)
def test_fingerprint_insensitive_to_case_and_whitespace(company: str, title: str, location: str) -> None:
    a = job_fingerprint(company, title, location, None)
    b = job_fingerprint(f"  {company.upper()} ", f"{title.lower()}  ", location.swapcase(), None)
    # swapcase/upper can change non-ASCII letters (e.g. 'ß' -> 'SS'), so compare via normalised keys
    if (
        normalize_company(company) == normalize_company(company.upper())
        and normalize_text(location) == normalize_text(location.swapcase())
        and normalize_text(title) == normalize_text(title.lower())
    ):
        assert a == b


@given(
    st.sampled_from(["utm_source", "utm_medium", "gh_src", "fbclid"]),
    st.text(alphabet="abc123", min_size=1, max_size=8),
)
def test_tracking_params_ignored(param: str, value: str) -> None:
    assert canonicalize_url(f"https://jobs.example.com/a?id=7&{param}={value}") == canonicalize_url(
        "https://jobs.example.com/a?id=7"
    )


@given(text, text)
def test_trigram_similarity_symmetric_and_bounded(a: str, b: str) -> None:
    s1, s2 = trigram_similarity(a, b), trigram_similarity(b, a)
    assert s1 == s2 and 0.0 <= s1 <= 1.0


skill_sets = st.sets(st.sampled_from(SKILLS), max_size=12)


def _profile(skills: set[str], years: float | None) -> ProfileInput:
    return ProfileInput(
        skills=set(skills),
        years_experience=years,
        education_level="bachelor",
        target_titles=["Engineer"],
        remote_preference="any",
    )


@settings(max_examples=150, suppress_health_check=[HealthCheck.too_slow])
@given(
    skill_sets, skill_sets, skill_sets, st.one_of(st.none(), st.floats(0, 30)), st.one_of(st.none(), st.floats(0, 15))
)
def test_score_bounds(
    user: set[str], req: set[str], pref: set[str], years: float | None, min_years: float | None
) -> None:
    r = score_job(
        _profile(user, years),
        JobInput(title="Engineer", required_skills=sorted(req), preferred_skills=sorted(pref), min_years=min_years),
    )
    assert 0.0 <= r.score <= 100.0
    assert 0.0 <= r.confidence <= 1.0


@settings(max_examples=150, suppress_health_check=[HealthCheck.too_slow])
@given(skill_sets, st.sets(st.sampled_from(SKILLS), min_size=1, max_size=10), st.sampled_from(SKILLS))
def test_adding_a_verified_skill_never_lowers_score(user: set[str], req: set[str], extra: str) -> None:
    job = JobInput(title="Engineer", required_skills=sorted(req))
    before = score_job(_profile(user, 3), job).score
    after = score_job(_profile(user | {extra}, 3), job).score
    assert after >= before


def test_uuid7_is_monotonic_and_versioned() -> None:
    """Ordering by id must reproduce insertion order (ties on created_at are broken by id)."""
    from app.db import uuid7

    ids = [uuid7() for _ in range(5000)]
    assert ids == sorted(ids)
    assert len(set(ids)) == len(ids)
    assert all(i.version == 7 and i.variant == "specified in RFC 4122" for i in ids)
