import itertools

import pytest

from app.services import state_machine as sm
from tests.conftest import FIXTURES, Api, onboard

# ------------------------------------------------------------------ state machine (unit)


def test_submitted_only_via_user_confirmation() -> None:
    for status in sm.STATUSES:
        for via in ("manual", "approval", "handoff", "system"):
            with pytest.raises(sm.TransitionError):
                sm.check_transition(status, "submitted_confirmed", via)
    sm.check_transition("awaiting_user_confirmation", "submitted_confirmed", "user_confirmation")


def test_gated_targets_require_their_action() -> None:
    with pytest.raises(sm.TransitionError):
        sm.check_transition("awaiting_approval", "approved", "manual")
    sm.check_transition("awaiting_approval", "approved", "approval")
    with pytest.raises(sm.TransitionError):
        sm.check_transition("approved", "handoff_opened", "manual")


def test_every_status_has_transitions_and_terminal_states_are_final() -> None:
    assert set(sm.TRANSITIONS) == set(sm.STATUSES)
    for t in sm.TERMINAL:
        assert sm.TRANSITIONS[t] == frozenset()
    for a, b in itertools.product(sm.STATUSES, sm.STATUSES):
        if b not in sm.TRANSITIONS[a]:
            with pytest.raises(sm.TransitionError):
                sm.check_transition(a, b, sm.GATED.get(b, "manual"))
    with pytest.raises(sm.TransitionError):
        sm.check_transition("saved", "nonsense")


def test_kanban_columns_cover_all_statuses() -> None:
    covered = [s for col in sm.KANBAN_COLUMNS.values() for s in col]
    assert sorted(covered) == sorted(sm.STATUSES)


def test_allowed_targets_excludes_gated() -> None:
    assert "approved" not in sm.allowed_targets("awaiting_approval")
    assert "submitted_confirmed" not in sm.allowed_targets("awaiting_user_confirmation")


# ------------------------------------------------------------------ workflow (API)


async def _setup(api: Api) -> tuple[str, str]:
    await onboard(api)
    r = await api.post("/api/jobs/import/manual_paste", {"text": (FIXTURES / "job_ml_engineer.txt").read_text("utf-8")})
    job_id = r.json()["created"][0]["id"]
    app = (await api.post("/api/applications", {"job_id": job_id})).json()
    return job_id, app["id"]


async def _to_awaiting_approval(api: Api, app_id: str) -> dict:  # type: ignore[type-arg]
    prep = await api.post(f"/api/applications/{app_id}/prepare")
    assert prep.status_code == 201 and prep.json()["grounded"], prep.text
    assert (await api.post(f"/api/applications/{app_id}/ready")).status_code == 200
    r = await api.post(f"/api/applications/{app_id}/request-approval")
    assert r.status_code == 200, r.text
    return r.json()


async def test_duplicate_application_blocked(api: Api) -> None:
    job_id, _ = await _setup(api)
    r = await api.post("/api/applications", {"job_id": job_id})
    assert r.status_code == 409 and r.json()["error"]["code"] == "duplicate_application"


async def test_full_workflow_requires_explicit_confirmation(api: Api) -> None:
    _, app_id = await _setup(api)
    approval = await _to_awaiting_approval(api, app_id)
    assert approval["preflight"]["ok"] and len(approval["payload_hash"]) == 64

    # Kanban/manual moves cannot jump to approved or submitted
    for target in ("approved", "submitted_confirmed", "handoff_opened"):
        r = await api.post(f"/api/applications/{app_id}/move", {"status": target})
        assert r.status_code == 409 and r.json()["error"]["code"] == "invalid_transition", target

    # Approval with a hash the user did not see is rejected
    bad = await api.post(f"/api/applications/{app_id}/approve", {"payload_hash": "0" * 64})
    assert bad.status_code == 409 and bad.json()["error"]["code"] == "payload_changed"

    ok = await api.post(f"/api/applications/{app_id}/approve", {"payload_hash": approval["payload_hash"]})
    assert ok.status_code == 200 and ok.json()["status"] == "approved"

    # Confirmation is impossible before hand-off
    early = await api.post(f"/api/applications/{app_id}/confirm-submission", {"confirmed": True})
    assert early.status_code == 409

    handoff = (await api.post(f"/api/applications/{app_id}/handoff")).json()
    assert "never clicks" in handoff["instructions"]
    app = (await api.get(f"/api/applications/{app_id}")).json()
    assert app["status"] == "awaiting_user_confirmation" and app["submitted_at"] is None

    # confirmed must be literally true
    assert (await api.post(f"/api/applications/{app_id}/confirm-submission", {"confirmed": False})).status_code == 422
    done = (
        await api.post(f"/api/applications/{app_id}/confirm-submission", {"confirmed": True, "note": "Done"})
    ).json()
    assert done["status"] == "submitted_confirmed" and done["submitted_at"]
    actions = [a["action"] for a in done["activity"]]
    assert actions.count("handoff") == 2 and "approval" in actions and "user_confirmation" in actions
    assert done["reminders"] and "Follow up" in done["reminders"][0]["message"]
    # Documents are locked after submission
    r = await api.put(f"/api/applications/{app_id}/documents", {"resume_doc_id": done["resume_doc_id"]})
    assert r.status_code == 409


async def test_edit_after_approval_invalidates_it(api: Api) -> None:
    _, app_id = await _setup(api)
    approval = await _to_awaiting_approval(api, app_id)
    await api.post(f"/api/applications/{app_id}/approve", {"payload_hash": approval["payload_hash"]})
    app = (await api.get(f"/api/applications/{app_id}")).json()
    doc = (await api.get(f"/api/documents/{app['resume_doc_id']}")).json()
    items = doc["content"]["items"]
    items.reverse()
    await api.put(f"/api/documents/{doc['id']}", {"items": items})
    app = (await api.get(f"/api/applications/{app_id}")).json()
    assert app["status"] == "ready_for_review"
    assert app["approvals"][0]["invalidated_at"] is not None
    assert (await api.post(f"/api/applications/{app_id}/handoff")).status_code == 409


async def test_sensitive_screening_questions_need_user_answers(api: Api) -> None:
    _, app_id = await _setup(api)
    await api.post(f"/api/applications/{app_id}/prepare")
    await api.post(f"/api/applications/{app_id}/ready")
    for q in (
        "Are you legally authorized to work in India?",
        "What are your salary expectations?",
        "Do you have experience with Python?",
        "Why do you want to join us?",
    ):
        await api.post(f"/api/applications/{app_id}/screening", {"question": q})
    app = (await api.get(f"/api/applications/{app_id}")).json()
    cats = {s["question"]: s for s in app["screening"]}
    assert cats["Are you legally authorized to work in India?"]["category"] == "sensitive_legal"
    assert cats["What are your salary expectations?"]["category"] == "sensitive_legal"
    assert cats["Are you legally authorized to work in India?"]["suggested_answer"] is None
    py = cats["Do you have experience with Python?"]
    assert py["category"] == "answerable_from_verified_facts" and py["supporting_fact_ids"]
    assert cats["Why do you want to join us?"]["category"] == "needs_user_input"
    assert all(not s["answered_by_user"] for s in app["screening"])

    r = await api.post(f"/api/applications/{app_id}/request-approval")
    assert r.status_code == 409 and r.json()["error"]["code"] == "preflight_failed"
    for s in app["screening"]:
        await api.put(
            f"/api/applications/{app_id}/screening/{s['id']}", {"answer": s["suggested_answer"] or "My answer"}
        )
    assert (await api.post(f"/api/applications/{app_id}/request-approval")).status_code == 200


async def test_preflight_blocks_ungrounded_resume(api: Api) -> None:
    _, app_id = await _setup(api)
    await api.post(f"/api/applications/{app_id}/prepare")
    app = (await api.get(f"/api/applications/{app_id}")).json()
    doc = (await api.get(f"/api/documents/{app['resume_doc_id']}")).json()
    items = doc["content"]["items"] + [{"section": "experience", "text": "Invented Python.", "supporting_fact_ids": []}]
    await api.put(f"/api/documents/{doc['id']}", {"items": items})
    await api.post(f"/api/applications/{app_id}/ready")
    r = await api.post(f"/api/applications/{app_id}/request-approval")
    assert r.status_code == 409
    checks = {c["name"]: c for c in r.json()["error"]["details"]["checks"]}
    assert checks["resume_grounded"]["blocking"] is True


async def test_post_submission_moves_undo_and_tracker(api: Api) -> None:
    _, app_id = await _setup(api)
    approval = await _to_awaiting_approval(api, app_id)
    await api.post(f"/api/applications/{app_id}/approve", {"payload_hash": approval["payload_hash"]})
    await api.post(f"/api/applications/{app_id}/handoff")
    await api.post(f"/api/applications/{app_id}/confirm-submission", {"confirmed": True})
    r = await api.post(f"/api/applications/{app_id}/move", {"status": "interviewing"})
    assert r.json()["status"] == "interviewing"
    assert (await api.post(f"/api/applications/{app_id}/undo")).json()["status"] == "submitted_confirmed"
    assert (await api.post(f"/api/applications/{app_id}/undo")).status_code == 409
    board = (await api.get("/api/applications")).json()
    assert board["items"][0]["status"] == "submitted_confirmed" and "Applied" in board["columns"]
    interviews = (await api.get("/api/interviews")).json()
    assert len(interviews) == 1
    notes = (await api.get("/api/notifications")).json()
    assert any("interviewing" in n["message"] for n in notes)


async def test_move_with_stale_etag_rejected(api: Api) -> None:
    _, app_id = await _setup(api)
    r = await api.post(f"/api/applications/{app_id}/move", {"status": "tailoring"}, headers={"If-Match": 'W/"99"'})
    assert r.status_code == 412


async def test_withdraw_and_terminal(api: Api) -> None:
    _, app_id = await _setup(api)
    assert (await api.post(f"/api/applications/{app_id}/move", {"status": "withdrawn"})).json()["status"] == "withdrawn"
    assert (await api.post(f"/api/applications/{app_id}/move", {"status": "saved"})).status_code == 409


async def test_reminders(api: Api) -> None:
    _, app_id = await _setup(api)
    r = await api.post(f"/api/applications/{app_id}/reminders", {"due_at": "2026-11-01T09:00:00Z", "message": "Ping"})
    rid = r.json()["id"]
    assert (await api.get("/api/reminders")).json()[0]["message"] == "Ping"
    await api.post(f"/api/reminders/{rid}/done")
    assert (await api.get("/api/reminders")).json() == []
