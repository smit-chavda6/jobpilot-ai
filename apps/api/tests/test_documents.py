import io

from tests.conftest import FIXTURES, Api, onboard


async def _job(api: Api) -> str:
    r = await api.post("/api/jobs/import/manual_paste", {"text": (FIXTURES / "job_ml_engineer.txt").read_text("utf-8")})
    return r.json()["created"][0]["id"]


async def test_tailored_resume_is_grounded_and_cites_facts(api: Api) -> None:
    facts = {f["id"] for f in await onboard(api)}
    job_id = await _job(api)
    r = await api.post("/api/documents", {"kind": "resume", "job_id": job_id})
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["grounded"] is True and doc["generator"] == "deterministic"
    assert doc["prompt_version"] == "tailor_resume@v1"
    for item in doc["content"]["items"]:
        assert item["supporting_fact_ids"] and set(item["supporting_fact_ids"]) <= facts
    kw = doc["keyword_report"]
    assert "Python" in kw["already_supported"] and "Kubernetes" not in kw["already_supported"]
    assert "Kubernetes" in kw["adjacent_ask_user"] + kw["unsupported"]
    # Skills matching the job are listed first in the tailored skills line
    skills_line = next(i for i in doc["content"]["items"] if i["section"] == "skill")["text"]
    assert skills_line.startswith("Python")


async def test_diff_with_provenance(api: Api) -> None:
    await onboard(api)
    job_id = await _job(api)
    doc_id = (await api.post("/api/documents", {"kind": "resume", "job_id": job_id})).json()["id"]
    d = (await api.get(f"/api/documents/{doc_id}")).json()
    assert d["diff"] and all(row["provenance"] for row in d["diff"])
    assert {row["status"] for row in d["diff"]} <= {"unchanged", "moved", "modified", "added", "removed"}


async def test_cover_letter_grounded_with_framing(api: Api) -> None:
    await onboard(api)
    job_id = await _job(api)
    doc = (await api.post("/api/documents", {"kind": "cover_letter", "job_id": job_id})).json()
    assert doc["grounded"] is True, doc["grounding_report"]
    kinds = {i["kind"] for i in doc["content"]["items"]}
    assert kinds == {"claim", "framing"}
    assert "Nimbus AI" in doc["content"]["items"][1]["text"]


async def test_hallucinated_edit_blocks_export(api: Api) -> None:
    await onboard(api)
    job_id = await _job(api)
    doc = (await api.post("/api/documents", {"kind": "resume", "job_id": job_id})).json()
    items = doc["content"]["items"]
    first = items[1]
    items[1] = {**first, "text": first["text"] + " Led a team of 12 engineers using Kubernetes."}
    r = await api.put(f"/api/documents/{doc['id']}", {"items": items}, headers={"If-Match": 'W/"1"'})
    assert r.status_code == 200
    edited = r.json()
    assert edited["grounded"] is False and edited["version"] == 2
    reasons = {x["code"] for x in edited["grounding_report"]["items"][first["id"]]["reasons"]}
    assert {"unsupported_number", "unsupported_entity", "inflation"} <= reasons
    exp = await api.get(f"/api/documents/{doc['id']}/export", params={"format": "pdf"})
    assert exp.status_code == 409 and exp.json()["error"]["code"] == "grounding_failed"
    assert exp.json()["error"]["details"]["failing_items"][0]["item_id"] == first["id"]
    # Stale If-Match is rejected
    stale = await api.put(f"/api/documents/{doc['id']}", {"items": items}, headers={"If-Match": 'W/"1"'})
    assert stale.status_code == 412


async def test_uncited_added_line_fails(api: Api) -> None:
    await onboard(api)
    doc = (await api.post("/api/documents", {"kind": "resume"})).json()
    items = doc["content"]["items"] + [
        {"section": "experience", "text": "Won a Kaggle competition.", "supporting_fact_ids": []}
    ]
    edited = (await api.put(f"/api/documents/{doc['id']}", {"items": items})).json()
    assert edited["grounded"] is False


async def test_pdf_and_docx_exports_open(api: Api) -> None:
    import docx
    from pypdf import PdfReader

    await onboard(api)
    job_id = await _job(api)
    doc = (await api.post("/api/documents", {"kind": "resume", "job_id": job_id})).json()
    pdf = await api.get(f"/api/documents/{doc['id']}/export", params={"format": "pdf"})
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
    text = "".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf.content)).pages)
    assert "Alex Rivera" in text and "churn" in text and "Experience" in text
    dx = await api.get(f"/api/documents/{doc['id']}/export", params={"format": "docx"})
    d = docx.Document(io.BytesIO(dx.content))
    body = "\n".join(p.text for p in d.paragraphs)
    assert "Alex Rivera" in body and "Skills" in body
    cover = (await api.post("/api/documents", {"kind": "cover_letter", "job_id": job_id})).json()
    assert (await api.get(f"/api/documents/{cover['id']}/export", params={"format": "docx"})).status_code == 200


async def test_generation_idempotency(api: Api) -> None:
    await onboard(api)
    h = {"Idempotency-Key": "gen-abcdefgh"}
    a = await api.post("/api/documents", {"kind": "resume"}, headers=h)
    b = await api.post("/api/documents", {"kind": "resume"}, headers=h)
    assert a.json()["id"] == b.json()["id"]
    assert len((await api.get("/api/documents")).json()) == 1
