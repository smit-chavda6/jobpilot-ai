import io
import zipfile

from tests.conftest import FIXTURES, Api, onboard


async def test_profile_etag_and_if_match(api: Api) -> None:
    r = await api.get("/api/profile")
    etag = r.headers["etag"]
    r = await api.patch("/api/profile", {"full_name": "Alex"}, headers={"If-Match": etag})
    assert r.status_code == 200
    stale = await api.patch("/api/profile", {"full_name": "Other"}, headers={"If-Match": etag})
    assert stale.status_code == 412
    assert stale.json()["error"]["code"] == "precondition_failed"


async def test_phone_is_encrypted_at_rest(api: Api) -> None:
    from sqlalchemy import select

    from app.db import get_sessionmaker
    from app.models import UserProfile

    await api.patch("/api/profile", {"phone": "+91 98765 43210"})
    assert (await api.get("/api/profile")).json()["phone"] == "+91 98765 43210"
    async with get_sessionmaker()() as s:
        stored = (await s.execute(select(UserProfile.phone_encrypted))).scalar_one()
    assert stored and "98765" not in stored


async def test_resume_parse_produces_candidate_facts(api: Api) -> None:
    r = await api.upload("/api/resumes", "resume.txt", (FIXTURES / "resume_alex.txt").read_bytes(), "text/plain")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["parse_status"] == "parsed"
    cats = {f["category"] for f in body["facts"]}
    assert {"experience", "education", "skill", "project", "certification", "summary"} <= cats
    assert all(f["status"] == "candidate" for f in body["facts"])
    exp = next(f for f in body["facts"] if "churn" in f["text"])
    assert exp["attributes"]["employer"] == "Acme Analytics" and exp["attributes"]["title"] == "Data Scientist"
    assert body["suggestions"]["detected_education_level"] == "master"


async def test_unconfirmed_facts_are_unusable_downstream(api: Api) -> None:
    await api.upload("/api/resumes", "resume.txt", (FIXTURES / "resume_alex.txt").read_bytes(), "text/plain")
    # No verified skills derived from candidate facts
    assert (await api.get("/api/skills")).json() == []
    # Document generation refuses to run on unconfirmed facts
    r = await api.post("/api/documents", {"kind": "resume"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "no_confirmed_facts"
    # Matching sees no verified skills
    imp = await api.post(
        "/api/jobs/import/manual_paste", {"text": (FIXTURES / "job_ml_engineer.txt").read_text(encoding="utf-8")}
    )
    job_id = imp.json()["created"][0]["id"]
    detail = (await api.get(f"/api/jobs/{job_id}")).json()
    assert detail["match_detail"]["explanation"]["matched_skills"] == []


async def test_confirm_reject_edit_and_manual_facts(api: Api) -> None:
    r = await api.upload("/api/resumes", "resume.txt", (FIXTURES / "resume_alex.txt").read_bytes(), "text/plain")
    facts = r.json()["facts"]
    py = next(f for f in facts if f["text"] == "Skill: Python")
    tab = next(f for f in facts if f["text"] == "Skill: Tableau")
    await api.post("/api/facts/status", {"fact_ids": [py["id"]], "status": "confirmed"})
    await api.post("/api/facts/status", {"fact_ids": [tab["id"]], "status": "rejected"})
    assert (await api.get("/api/skills")).json() == ["Python"]
    r = await api.post("/api/facts", {"category": "skill", "text": "Skill: Go", "attributes": {"skill": "Go"}})
    assert r.status_code == 201 and r.json()["status"] == "confirmed" and r.json()["source"] == "manual"
    assert "Go" in (await api.get("/api/skills")).json()
    r = await api.patch(f"/api/facts/{tab['id']}", {"text": "Skill: Tableau (basic)"})
    assert r.json()["status"] == "confirmed"
    assert (await api.delete(f"/api/facts/{py['id']}")).status_code == 204
    assert "Python" not in (await api.get("/api/skills")).json()


async def test_consent_records(api: Api) -> None:
    await api.post("/api/consents", {"purpose": "ai_processing", "granted": True})
    await api.post("/api/consents", {"purpose": "ai_processing", "granted": False})
    state = (await api.get("/api/consents")).json()
    assert state["consents"]["ai_processing"]["granted"] is False
    assert state["ai_provider"] == "mock" and state["data_sent_to_provider"] == []


# ------------------------------------------------------------------ upload corpus


def _docx(extra: dict[str, bytes] | None = None, content_types: bytes | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types or b"<Types></Types>")
        z.writestr("word/document.xml", b"<w:document/>")
        for k, v in (extra or {}).items():
            z.writestr(k, v)
    return buf.getvalue()


async def test_upload_corpus_rejected(api: Api) -> None:
    cases = {
        "malware.exe": (b"MZ\x90\x00", "application/octet-stream"),
        "fake.pdf": (b"not a pdf at all", "application/pdf"),
        "script.pdf": (b"%PDF-1.4\n1 0 obj << /OpenAction 2 0 R /JavaScript (app.alert(1)) >>", "application/pdf"),
        "mismatch.txt": (b"hello", "application/pdf"),
        "binary.txt": (b"abc\x00def", "text/plain"),
        "empty.txt": (b"", "text/plain"),
        "macro.docx": (_docx({"word/vbaProject.bin": b"\x00" * 10}), "application/octet-stream"),
        "macro2.docx": (
            _docx(content_types=b"<Types>application/vnd.ms-word.document.macroEnabled</Types>"),
            "application/octet-stream",
        ),
        "bomb.docx": (_docx({"word/huge.xml": b"0" * (60 * 1024 * 1024)}), "application/octet-stream"),
        "notzip.docx": (b"PK\x03\x04garbage", "application/octet-stream"),
    }
    for name, (data, mime) in cases.items():
        r = await api.upload("/api/resumes", name, data, mime)
        assert r.status_code == 422, (name, r.status_code, r.text)
        assert r.json()["error"]["code"] == "upload_rejected", name


async def test_oversized_upload_rejected(api: Api) -> None:
    r = await api.upload("/api/resumes", "big.txt", b"a" * (5 * 1024 * 1024 + 1), "text/plain")
    assert r.status_code == 422


async def test_docx_and_pdf_resumes_parse(api: Api) -> None:
    import docx
    from reportlab.pdfgen import canvas

    d = docx.Document()
    for line in [
        "Sam Lee",
        "EXPERIENCE",
        "Software Engineer — Initech (2021 – Present)",
        "- Built REST APIs in Python and FastAPI.",
        "SKILLS",
        "Python, Docker",
    ]:
        d.add_paragraph(line)
    buf = io.BytesIO()
    d.save(buf)
    r = await api.upload(
        "/api/resumes",
        "cv.docx",
        buf.getvalue(),
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    assert r.status_code == 201 and any("REST APIs" in f["text"] for f in r.json()["facts"])

    pbuf = io.BytesIO()
    c = canvas.Canvas(pbuf)
    for i, line in enumerate(["Sam Lee", "SKILLS", "Python, SQL, Docker"]):
        c.drawString(72, 750 - 18 * i, line)
    c.save()
    r = await api.upload("/api/resumes", "cv.pdf", pbuf.getvalue(), "application/pdf")
    assert r.status_code == 201
    assert {"Skill: Python", "Skill: SQL"} <= {f["text"] for f in r.json()["facts"]}


async def test_stored_files_use_random_keys(api: Api) -> None:
    from app.config import get_settings

    await api.upload("/api/resumes", "../../etc/passwd.txt", b"SKILLS\nPython", "text/plain")
    files = list(get_settings().upload_dir.iterdir())
    assert len(files) == 1 and "passwd" not in files[0].name and files[0].suffix == ".bin"
    resumes = (await api.get("/api/resumes")).json()
    assert resumes[0]["filename"] == "passwd.txt"


async def test_onboarding_helper(api: Api) -> None:
    facts = await onboard(api)
    assert len(facts) > 10
    p = (await api.get("/api/profile")).json()
    assert p["onboarding_completed"] is True
