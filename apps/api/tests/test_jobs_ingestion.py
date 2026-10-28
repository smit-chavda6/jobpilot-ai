from pathlib import Path

import pytest

from app.adapters import sources
from app.services.safe_fetch import FetchResult
from tests.conftest import FIXTURES, Api, onboard

JD = (FIXTURES / "job_ml_engineer.txt").read_text(encoding="utf-8")


async def test_paste_import_extracts_structure(api: Api) -> None:
    r = await api.post("/api/jobs/import/manual_paste", {"text": JD})
    assert r.status_code == 201, r.text
    job_id = r.json()["created"][0]["id"]
    j = (await api.get(f"/api/jobs/{job_id}")).json()
    assert j["title"] == "Machine Learning Engineer" and j["company"] == "Nimbus AI"
    assert j["remote_policy"] == "hybrid" and j["employment_type"] == "full_time"
    assert j["salary_min"] == 2_500_000 and j["salary_currency"] == "INR"
    assert j["min_years"] == 3 and j["education_req"] == "bachelor"
    assert "Python" in j["required_skills"] and "Kubernetes" in j["preferred_skills"]
    assert j["match_detail"] is not None  # matched asynchronously via the outbox (inline in tests)


async def test_reimport_is_idempotent(api: Api) -> None:
    first = (await api.post("/api/jobs/import/manual_paste", {"text": JD})).json()
    second = (await api.post("/api/jobs/import/manual_paste", {"text": JD})).json()
    assert first["counts"]["created"] == 1 and second["counts"] == {"created": 0, "updated": 1, "failed": 0}
    assert len((await api.get("/api/jobs")).json()["items"]) == 1


async def test_idempotency_key_replays_response(api: Api) -> None:
    h = {"Idempotency-Key": "key-123456789"}
    a = await api.post("/api/jobs/import/manual_paste", {"text": JD}, headers=h)
    b = await api.post("/api/jobs/import/manual_paste", {"text": JD}, headers=h)
    assert a.json() == b.json() and b.headers.get("idempotent-replayed") == "true"
    c = await api.post("/api/jobs/import/manual_paste", {"text": JD + "\nextra"}, headers=h)
    assert c.status_code == 409 and c.json()["error"]["code"] == "idempotency_mismatch"


async def test_csv_import_with_failed_row(api: Api) -> None:
    r = await api.upload("/api/jobs/import/file", "jobs.csv", (FIXTURES / "jobs.csv").read_bytes(), "text/csv")
    body = r.json()
    assert body["counts"] == {"created": 2, "updated": 0, "failed": 1}
    failed = (await api.get("/api/jobs/failed-imports")).json()
    assert len(failed) == 1 and failed[0]["stage"] == "normalize"
    assert (await api.post(f"/api/jobs/failed-imports/{failed[0]['id']}/resolve")).status_code == 200
    assert (await api.get("/api/jobs/failed-imports")).json() == []


async def test_json_import(api: Api) -> None:
    r = await api.upload(
        "/api/jobs/import/file", "jobs.json", (FIXTURES / "jobs.json").read_bytes(), "application/json"
    )
    assert r.json()["counts"]["created"] == 2
    bad = await api.upload("/api/jobs/import/file", "bad.json", b"{not json", "application/json")
    assert bad.json()["counts"]["failed"] == 1


async def test_url_tracking_params_dedup() -> None:
    from app.services.fingerprint import canonicalize_url, job_fingerprint

    a = job_fingerprint(
        "Fabrikam Inc.", "Backend Engineer", "Pune, India", "https://jobs.example.com/fabrikam/backend?utm_source=feed"
    )
    b = job_fingerprint("fabrikam", "backend engineer", "pune india", "http://www.jobs.example.com/fabrikam/backend/")
    assert a == b
    assert canonicalize_url("https://x.com/a?b=1&utm_campaign=z") == "https://x.com/a?b=1"


async def test_fuzzy_duplicate_flagged_not_merged(api: Api) -> None:
    await api.post(
        "/api/jobs/import/manual_paste", {"text": "Senior Data Scientist at Globex Corporation\nPython, SQL"}
    )
    r = await api.post(
        "/api/jobs/import/manual_paste",
        {"text": "Sr. Data Scientist at Globex\nPython, SQL", "url": "https://other.example/job/9"},
    )
    created = r.json()["created"][0]
    assert created["potential_duplicate"] is True
    assert len((await api.get("/api/jobs")).json()["items"]) == 2


async def test_email_alert_import(api: Api) -> None:
    r = await api.upload("/api/jobs/import/email", "alert.eml", (FIXTURES / "email_alert.eml").read_bytes())
    body = r.json()
    assert body["counts"]["created"] == 3
    titles = {j["title"] for j in (await api.get("/api/jobs")).json()["items"]}
    companies = {j["company"] for j in (await api.get("/api/jobs")).json()["items"]}
    assert "Senior Data Scientist" in titles and {"Umbrella Corp", "Stark Industries", "Wayne Enterprises"} == companies


@pytest.fixture
def fake_fetch(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    calls: list[str] = []
    pages: dict[str, tuple[str, str]] = {}

    async def _fake(url: str, **_: object) -> FetchResult:
        calls.append(url)
        for prefix, (ctype, text) in pages.items():
            if url.startswith(prefix):
                return FetchResult(url, 200, ctype, text)
        from app.errors import UnprocessableError

        raise UnprocessableError("The page returned HTTP 404", code="fetch_failed", details={"status": 404})

    monkeypatch.setattr(sources, "safe_get_with_retry", _fake)
    return pages, calls


async def test_greenhouse_public_board(api: Api, fake_fetch) -> None:  # type: ignore[no-untyped-def]
    pages, calls = fake_fetch
    pages["https://boards-api.greenhouse.io/v1/boards/acmeco/jobs"] = (
        "application/json",
        (FIXTURES / "greenhouse_board.json").read_text(),
    )
    r = await api.post("/api/jobs/import/greenhouse", {"board": "acmeco"})
    assert r.json()["counts"]["created"] == 2
    items = (await api.get("/api/jobs", params={"sort": "recent"})).json()["items"]
    assert all(i["verification_status"] == "verified_live" and i["source"] == "greenhouse" for i in items)
    detail = (await api.get(f"/api/jobs/{items[0]['id']}")).json()
    assert "<script" not in detail["description_html"]
    bad = await api.post("/api/jobs/import/greenhouse", {"board": "../../etc"})
    assert bad.json()["counts"]["failed"] == 1


async def test_lever_and_ashby(api: Api, fake_fetch) -> None:  # type: ignore[no-untyped-def]
    import json

    pages, _ = fake_fetch
    pages["https://api.lever.co/v0/postings/acme"] = (
        "application/json",
        json.dumps(
            [
                {
                    "id": "abc",
                    "text": "Data Engineer",
                    "hostedUrl": "https://jobs.lever.co/acme/abc",
                    "categories": {"location": "Remote", "commitment": "Full-time"},
                    "description": "<p>Spark and Airflow</p>",
                    "lists": [{"text": "Requirements", "content": "<li>3+ years of experience</li>"}],
                    "workplaceType": "remote",
                    "salaryRange": {"min": 100000, "max": 140000, "currency": "USD"},
                }
            ]
        ),
    )
    pages["https://api.ashbyhq.com/posting-api/job-board/acme"] = (
        "application/json",
        json.dumps(
            {
                "jobs": [
                    {
                        "id": "x1",
                        "title": "ML Researcher",
                        "location": "London",
                        "employmentType": "FullTime",
                        "isRemote": False,
                        "descriptionHtml": "<p>PyTorch</p>",
                        "jobUrl": "https://jobs.ashbyhq.com/acme/x1",
                    }
                ]
            }
        ),
    )
    assert (await api.post("/api/jobs/import/lever", {"company": "acme"})).json()["counts"]["created"] == 1
    assert (await api.post("/api/jobs/import/ashby", {"organization": "acme"})).json()["counts"]["created"] == 1
    items = {i["title"]: i for i in (await api.get("/api/jobs")).json()["items"]}
    assert items["Data Engineer"]["remote_policy"] == "remote" and items["Data Engineer"]["salary_max"] == 140000
    assert items["ML Researcher"]["employment_type"] == "full_time"


async def test_url_import_json_ld(api: Api, fake_fetch) -> None:  # type: ignore[no-untyped-def]
    pages, _ = fake_fetch
    pages["https://careers.example.com/job/42"] = (
        "text/html",
        """<html><head><title>Job</title>
    <script type="application/ld+json">{"@context":"https://schema.org","@type":"JobPosting","title":"Analytics Engineer",
    "hiringOrganization":{"name":"Hooli"},"jobLocation":{"address":{"addressLocality":"Austin","addressCountry":"US"}},
    "description":"<p>dbt, SQL and Snowflake. 2+ years of experience.</p>",
    "baseSalary":{"currency":"USD","value":{"minValue":120000,"maxValue":150000}}}</script></head><body></body></html>""",
    )
    r = await api.post("/api/jobs/import/manual_url", {"url": "https://careers.example.com/job/42"})
    job = r.json()["created"][0]
    detail = (await api.get(f"/api/jobs/{job['id']}")).json()
    assert detail["company"] == "Hooli" and detail["salary_max"] == 150000 and "dbt" in detail["required_skills"]


async def test_rss_feed(api: Api, fake_fetch) -> None:  # type: ignore[no-untyped-def]
    pages, _ = fake_fetch
    pages["https://feeds.example.com/jobs.xml"] = (
        "application/rss+xml",
        """<?xml version="1.0"?><rss><channel>
      <item><title>Platform Engineer at Pied Piper</title><link>https://pp.example/jobs/1</link>
      <description>Kubernetes and Terraform</description><pubDate>Mon, 26 Oct 2026 10:00:00 GMT</pubDate></item>
    </channel></rss>""",
    )
    r = await api.post("/api/jobs/import/rss", {"url": "https://feeds.example.com/jobs.xml"})
    assert r.json()["counts"]["created"] == 1
    item = (await api.get("/api/jobs")).json()["items"][0]
    assert item["company"] == "Pied Piper"


async def test_rss_xml_bomb_rejected(api: Api, fake_fetch) -> None:  # type: ignore[no-untyped-def]
    pages, _ = fake_fetch
    pages["https://feeds.example.com/bomb.xml"] = (
        "application/xml",
        """<?xml version="1.0"?>
    <!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;&lol;">]><rss><channel><item>
    <title>&lol2;</title></item></channel></rss>""",
    )
    r = await api.post("/api/jobs/import/rss", {"url": "https://feeds.example.com/bomb.xml"})
    assert r.json()["counts"]["failed"] == 1


async def test_sources_registry_and_toggle(api: Api) -> None:
    reg = (await api.get("/api/sources")).json()
    ids = {s["id"] for s in reg["sources"]}
    assert {"greenhouse", "lever", "ashby", "manual_url", "manual_paste", "file_import", "rss", "email_upload"} <= ids
    disabled = {d["id"] for d in reg["disabled_by_policy"]}
    assert {"linkedin", "indeed"} <= disabled
    assert all(d["manual_path"] for d in reg["disabled_by_policy"])
    assert (await api.put("/api/sources/greenhouse", {"enabled": False})).json()["enabled"] is False
    r = await api.post("/api/jobs/import/greenhouse", {"board": "acmeco"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "source_disabled"


async def test_unknown_source_rejected(api: Api) -> None:
    r = await api.post("/api/jobs/import/linkedin", {"url": "https://linkedin.com/jobs/1"})
    assert r.status_code == 422


async def test_scam_signals_on_job(api: Api) -> None:
    text = (
        "Data Entry Assistant at QuickCash Ltd\nWork from home, earn $4000 per week, no experience needed. "
        "Pay a registration fee of $50. Contact recruiter on WhatsApp. Email: quickcash.hr@gmail.com"
    )
    r = await api.post("/api/jobs/import/manual_paste", {"text": text})
    job = (await api.get(f"/api/jobs/{r.json()['created'][0]['id']}")).json()
    report = job["scam_report"]
    codes = {s["code"] for s in report["signals"]}
    assert {"upfront_fee", "off_platform_chat", "free_mail_recruiter", "implausible_pay"} <= codes
    assert report["level"] == "high"
    assert "fraudulent" in report["summary"] and "does not mean it is fraudulent" in report["summary"]
    fb = await api.post(f"/api/jobs/{job['id']}/scam-feedback", {"signal_code": "off_platform_chat"})
    assert fb.status_code == 201
    job = (await api.get(f"/api/jobs/{job['id']}")).json()
    assert any(s.get("reported_false_positive") for s in job["scam_report"]["signals"])


async def test_list_filters_and_cursor_pagination(api: Api) -> None:
    await onboard(api)
    for i in range(7):
        await api.post("/api/jobs/import/manual_paste", {"text": f"Data Scientist {i} at Co{i}\nPython SQL"})
    seen: list[str] = []
    cursor = None
    while True:
        params = {"limit": 3, **({"cursor": cursor} if cursor else {})}
        page = (await api.get("/api/jobs", params=params)).json()
        seen += [i["id"] for i in page["items"]]
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert len(seen) == 7 == len(set(seen))
    scores = [i["match"]["score"] for i in (await api.get("/api/jobs")).json()["items"]]
    assert scores == sorted(scores, reverse=True)
    assert len((await api.get("/api/jobs", params={"q": "co3"})).json()["items"]) == 1


async def test_bulk_actions(api: Api) -> None:
    r = await api.upload(
        "/api/jobs/import/file", "jobs.json", (FIXTURES / "jobs.json").read_bytes(), "application/json"
    )
    ids = [c["id"] for c in r.json()["created"]]
    assert (await api.post("/api/jobs/bulk", {"job_ids": ids, "action": "save_to_tracker"})).json()["done"] == 2
    again = (await api.post("/api/jobs/bulk", {"job_ids": ids, "action": "save_to_tracker"})).json()
    assert again == {"done": 0, "skipped": 2}
    await api.post("/api/jobs/bulk", {"job_ids": ids[:1], "action": "archive"})
    assert len((await api.get("/api/jobs")).json()["items"]) == 1


async def test_saved_filters(api: Api) -> None:
    await api.put("/api/saved-filters", [{"name": "Remote DS", "params": {"q": "data", "remote": "remote"}}])
    assert (await api.get("/api/saved-filters")).json()[0]["name"] == "Remote DS"


def test_fixture_dir_exists() -> None:
    assert Path(FIXTURES).is_dir()
