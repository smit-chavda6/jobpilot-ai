from tests.conftest import FIXTURES, Api, onboard
from tests.test_applications import _setup, _to_awaiting_approval


async def _submitted(api: Api) -> str:
    _, app_id = await _setup(api)
    approval = await _to_awaiting_approval(api, app_id)
    await api.post(f"/api/applications/{app_id}/approve", {"payload_hash": approval["payload_hash"]})
    await api.post(f"/api/applications/{app_id}/handoff")
    await api.post(f"/api/applications/{app_id}/confirm-submission", {"confirmed": True})
    return app_id


async def test_interview_invite_suggestion_requires_acceptance(api: Api) -> None:
    app_id = await _submitted(api)
    r = await api.upload("/api/triage/upload", "invite.eml", (FIXTURES / "email_interview.eml").read_bytes())
    assert r.status_code == 201
    email = r.json()[0]
    assert email["classification"] == "interview_invite" and email["application_id"] == app_id
    assert email["suggested_status"] == "interviewing" and email["review_status"] == "pending"
    assert "interview" in email["evidence"].lower() and email["draft_reply"].startswith("Subject: Re:")
    # Nothing changed until the user accepts
    assert (await api.get(f"/api/applications/{app_id}")).json()["status"] == "submitted_confirmed"
    acc = (await api.post(f"/api/triage/{email['id']}/accept")).json()
    assert acc["application_status"] == "interviewing"
    app = (await api.get(f"/api/applications/{app_id}")).json()
    last = app["activity"][-1]
    assert last["detail"]["source"] == "email_triage" and last["detail"]["message_id"] == "<invite-001@nimbusai.com>"
    assert (await api.post(f"/api/triage/{email['id']}/accept")).status_code == 409


async def test_rejection_and_dismiss(api: Api) -> None:
    await _submitted(api)
    email = (await api.upload("/api/triage/upload", "r.eml", (FIXTURES / "email_rejection.eml").read_bytes())).json()[0]
    assert email["classification"] == "rejection" and email["suggested_status"] == "rejected"
    d = (await api.post(f"/api/triage/{email['id']}/dismiss")).json()
    assert d["review_status"] == "dismissed"


async def test_no_suggestion_for_unsubmitted_application(api: Api) -> None:
    await _setup(api)  # application exists but not submitted
    email = (
        await api.upload("/api/triage/upload", "invite.eml", (FIXTURES / "email_interview.eml").read_bytes())
    ).json()[0]
    assert email["classification"] == "interview_invite" and email["suggested_status"] is None


async def test_reupload_is_deduplicated_and_scam_email_flagged(api: Api) -> None:
    await api.upload("/api/triage/upload", "s.eml", (FIXTURES / "email_scam.eml").read_bytes())
    again = (await api.upload("/api/triage/upload", "s.eml", (FIXTURES / "email_scam.eml").read_bytes())).json()
    assert len((await api.get("/api/triage")).json()) == 1
    report = again[0]["scam_report"]
    codes = {s["code"] for s in report["signals"]}
    assert {"upfront_fee", "sensitive_ids", "off_platform_chat", "no_interview_offer"} <= codes
    assert report["level"] == "high"


async def test_job_alert_email_classified_and_importable(api: Api) -> None:
    email = (await api.upload("/api/triage/upload", "a.eml", (FIXTURES / "email_alert.eml").read_bytes())).json()[0]
    assert email["classification"] == "job_alert"


async def test_mbox_upload(api: Api) -> None:
    mbox = b""
    for name in ("email_interview.eml", "email_rejection.eml"):
        mbox += (
            b"From sender@example.com Mon Oct 26 10:00:00 2026\n"
            + (FIXTURES / name).read_bytes().replace(b"\r\n", b"\n")
            + b"\n"
        )
    r = await api.upload("/api/triage/upload", "box.mbox", mbox)
    assert {e["classification"] for e in r.json()} == {"interview_invite", "rejection"}


async def test_invalid_email_upload(api: Api) -> None:
    assert (await api.upload("/api/triage/upload", "x.pdf", b"%PDF-")).status_code == 422


async def test_interview_prep_bank_star_and_mock_session(api: Api) -> None:
    await onboard(api)
    r = await api.post("/api/jobs/import/manual_paste", {"text": (FIXTURES / "job_ml_engineer.txt").read_text("utf-8")})
    job_id = r.json()["created"][0]["id"]
    bank = (await api.get("/api/interview-prep/bank", params={"job_id": job_id})).json()
    assert {"technical", "coding", "project", "behavioral"} <= set(bank)
    assert any("Python" in q["question"] for q in bank["technical"])

    star = (
        await api.post(
            "/api/interview-prep/star",
            {"question": "Tell me about a machine learning model you built with XGBoost", "job_id": job_id},
        )
    ).json()
    assert star["supporting_fact_ids"] and "XGBoost" in star["action"]
    assert "Acme Analytics" in star["situation"] and "18" in star["result"]

    s = (await api.post("/api/interview-prep/sessions", {"job_id": job_id, "questions": 3})).json()
    assert len(s["questions"]) == 3
    good = (
        "When I was a data scientist at Acme Analytics, my goal was to reduce churn. I built a churn model with Python "
        "and XGBoost and set up Airflow pipelines. As a result, campaign precision improved by 18%."
    )
    fb = (
        await api.post(
            f"/api/interview-prep/sessions/{s['id']}/answers", {"question_id": s["questions"][0]["id"], "answer": good}
        )
    ).json()["feedback"]
    weak = (
        await api.post(
            f"/api/interview-prep/sessions/{s['id']}/answers",
            {"question_id": s["questions"][1]["id"], "answer": "um I like basically did stuff"},
        )
    ).json()["feedback"]
    assert fb["overall"] > weak["overall"]
    assert weak["tips"] and set(fb["scores"]) == {"relevance", "structure", "specificity", "clarity"}
    last = await api.post(
        f"/api/interview-prep/sessions/{s['id']}/answers", {"question_id": s["questions"][2]["id"], "answer": good}
    )
    sess = last.json()["session"]
    assert sess["completed"] and sess["overall_score"] is not None
    assert (
        await api.post(f"/api/interview-prep/sessions/{s['id']}/answers", {"question_id": "q1", "answer": "again"})
    ).status_code == 409
    trend = (await api.get("/api/interview-prep/sessions")).json()
    assert len(trend) == 1
