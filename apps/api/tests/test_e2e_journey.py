"""Definition-of-Done journey through the HTTP API:
register -> onboard -> upload & confirm resume -> import job -> view match -> tailor -> review ->
approve -> hand-off -> confirm submission -> tracker history -> analytics."""

from tests.conftest import FIXTURES, PASSWORD, Api


async def test_full_user_journey(make_api) -> None:  # type: ignore[no-untyped-def]
    api: Api = await make_api()
    # Register
    assert (
        await api.post("/api/auth/register", {"email": "journey@example.com", "password": PASSWORD})
    ).status_code == 201
    # Onboarding wizard: consent -> profile -> preferences -> resume -> confirm facts
    await api.post("/api/consents", {"purpose": "ai_processing", "granted": True})
    await api.patch(
        "/api/profile",
        {"full_name": "Alex Rivera", "years_experience": 4, "education_level": "master", "onboarding_step": 2},
    )
    await api.patch(
        "/api/profile",
        {
            "target_titles": ["Machine Learning Engineer"],
            "preferred_locations": ["Bengaluru"],
            "employment_types": ["full_time"],
            "onboarding_step": 3,
        },
    )
    up = await api.upload("/api/resumes", "resume.txt", (FIXTURES / "resume_alex.txt").read_bytes(), "text/plain")
    facts = up.json()["facts"]
    await api.post("/api/facts/status", {"fact_ids": [f["id"] for f in facts], "status": "confirmed"})
    await api.patch("/api/profile", {"onboarding_step": 5, "onboarding_completed": True})
    dash = (await api.get("/api/dashboard")).json()
    assert dash["onboarding_completed"] and dash["counts"]["confirmed_facts"] == len(facts)

    # Import job (permitted source) and see an explained match
    imp = await api.post(
        "/api/jobs/import/manual_paste",
        {"text": (FIXTURES / "job_ml_engineer.txt").read_text("utf-8")},
        headers={"Idempotency-Key": "journey-import-1"},
    )
    job_id = imp.json()["created"][0]["id"]
    job = (await api.get(f"/api/jobs/{job_id}")).json()
    assert job["match"]["recommended_action"] in ("apply", "apply_after_tailoring")
    assert job["match_detail"]["explanation"]["fit_reasons"]

    # Prepare application: tailored resume + cover letter, both grounded
    app_id = (await api.post("/api/applications", {"job_id": job_id})).json()["id"]
    prep = (await api.post(f"/api/applications/{app_id}/prepare")).json()
    assert prep["grounded"]

    # Edit the resume in the studio (reorder) - still grounded, still exportable
    doc = (await api.get(f"/api/documents/{prep['resume_doc_id']}")).json()
    items = doc["content"]["items"]
    items[1], items[2] = items[2], items[1]
    edited = (await api.put(f"/api/documents/{doc['id']}", {"items": items})).json()
    assert edited["grounded"]
    assert (await api.get(f"/api/documents/{doc['id']}/export", params={"format": "pdf"})).status_code == 200

    # Review -> approve -> hand-off -> user confirms submission
    await api.post(f"/api/applications/{app_id}/ready")
    review = (await api.post(f"/api/applications/{app_id}/request-approval")).json()
    await api.post(f"/api/applications/{app_id}/approve", {"payload_hash": review["payload_hash"]})
    handoff = (await api.post(f"/api/applications/{app_id}/handoff")).json()
    assert "submit" in handoff["instructions"]
    final = (await api.post(f"/api/applications/{app_id}/confirm-submission", {"confirmed": True})).json()
    assert final["status"] == "submitted_confirmed"

    # Tracker shows it with full history
    board = (await api.get("/api/applications")).json()
    assert board["items"][0]["id"] == app_id and board["items"][0]["status"] == "submitted_confirmed"
    history = [(a["from"], a["to"]) for a in final["activity"] if a["to"]]
    assert history[0] == (None, "saved") and history[-1] == ("awaiting_user_confirmation", "submitted_confirmed")

    # Analytics derived from stored records
    a = (await api.get("/api/analytics")).json()
    assert a["totals"]["submitted"] == 1 and a["by_status"] == {"submitted_confirmed": 1}
    assert a["response_rate"]["insufficient_data"] is True
