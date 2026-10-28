import io
import json
import zipfile

from sqlalchemy import func, select

from app.config import get_settings
from app.db import get_sessionmaker
from app.models import USER_OWNED_MODELS, User
from tests.conftest import PASSWORD, Api, onboard
from tests.test_authz_sweep import _victim


async def test_export_contains_all_data_without_secrets(api: Api) -> None:
    await _victim(api)
    await api.post("/api/auth/reauth", {"password": PASSWORD})
    r = await api.post("/api/privacy/export")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    z = zipfile.ZipFile(io.BytesIO(r.content))
    data = json.loads(z.read("data.json"))
    assert data["user"]["email"] == "alice@example.com"
    for table in (
        "profile_facts",
        "jobs",
        "applications",
        "generated_documents",
        "email_messages",
        "application_activities",
    ):
        assert data[table], table
    raw = z.read("data.json").decode()
    assert "password_hash" not in raw and "token_hash" not in raw and "$argon2" not in raw
    assert any(n.startswith("files/") for n in z.namelist())


async def test_verified_hard_deletion(api: Api, make_api) -> None:  # type: ignore[no-untyped-def]
    await _victim(api)
    bystander: Api = await make_api("bystander@example.com")
    await onboard(bystander)
    assert any(get_settings().upload_dir.iterdir())

    assert (await api.post("/api/privacy/delete-account", {"confirm": "DELETE"})).status_code == 403  # needs re-auth
    await api.post("/api/auth/reauth", {"password": PASSWORD})
    assert (await api.post("/api/privacy/delete-account", {"confirm": "yes"})).status_code == 422
    r = await api.post("/api/privacy/delete-account", {"confirm": "DELETE"})
    assert r.status_code == 200, r.text
    report = r.json()
    assert report["verified"] is True and report["files_deleted"] >= 1
    assert report["deleted_rows"]["job_embeddings"] >= 1 and report["deleted_rows"]["ai_usage_logs"] >= 0

    async with get_sessionmaker()() as s:
        assert (
            await s.execute(select(func.count()).select_from(User).where(User.email == "alice@example.com"))
        ).scalar_one() == 0
        bystander_id = (await s.execute(select(User.id).where(User.email == "bystander@example.com"))).scalar_one()
        for model in USER_OWNED_MODELS:
            others = (
                await s.execute(select(func.count()).select_from(model).where(model.user_id != bystander_id))
            ).scalar_one()  # type: ignore[attr-defined]
            assert others == 0, model.__tablename__
    # bystander data intact; deleted user's session is dead
    assert len((await bystander.get("/api/facts")).json()) > 10
    assert (await api.get("/api/auth/me")).status_code == 401
    assert (await api.post("/api/auth/login", {"email": "alice@example.com", "password": PASSWORD})).status_code == 401
