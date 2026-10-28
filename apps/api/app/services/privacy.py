"""Full data export (JSON + files) and verified hard deletion (spec §15)."""

from __future__ import annotations

import io
import json
import uuid
import zipfile
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, func, inspect, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import USER_OWNED_MODELS, Resume, User
from app.services import uploads

EXCLUDED_COLUMNS = {"password_hash", "token_hash", "token_encrypted", "phone_encrypted", "request_hash"}

# Children before parents so deletion works even without FK cascades.
DELETE_ORDER = [
    "ScreeningAnswer",
    "ApprovalRecord",
    "ApplicationActivity",
    "Reminder",
    "Interview",
    "RecruiterContact",
    "EmailMessage",
    "Application",
    "GeneratedDocument",
    "MockInterviewSession",
    "ScamFeedback",
    "JobMatch",
    "JobEmbedding",
    "FailedImport",
    "Job",
    "UserSkill",
    "ProfileFact",
    "Resume",
    "Notification",
    "OutboxEvent",
    "IdempotencyRecord",
    "AIUsageLog",
    "AuditLog",
    "ConsentRecord",
    "UserIntegration",
    "UserSettings",
    "UserProfile",
    "DevMailbox",
    "AuthToken",
]


def _row(obj: Any) -> dict[str, Any]:
    out = {}
    for col in inspect(obj).mapper.column_attrs:
        if col.key in EXCLUDED_COLUMNS:
            continue
        v = getattr(obj, col.key)
        out[col.key] = v.isoformat() if isinstance(v, datetime) else str(v) if isinstance(v, uuid.UUID) else v
    return out


async def export_user(session: AsyncSession, user: User) -> bytes:
    data: dict[str, Any] = {
        "exported_at": datetime.now(UTC).isoformat(),
        "format": "jobpilot-export@1",
        "user": {
            "id": str(user.id),
            "email": user.email,
            "email_verified": user.email_verified,
            "created_at": user.created_at.isoformat(),
        },
        "ai_provider": get_settings().llm_provider,
    }
    for model in USER_OWNED_MODELS:
        rows = (await session.execute(select(model).where(model.user_id == user.id))).scalars().all()  # type: ignore[attr-defined]
        data[model.__tablename__] = [_row(r) for r in rows]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("data.json", json.dumps(data, indent=2, default=str))
        for r in (await session.execute(select(Resume).where(Resume.user_id == user.id))).scalars().all():
            try:
                zf.writestr(f"files/{r.id}_{r.filename}", uploads.load(r.storage_key))
            except (FileNotFoundError, ValueError):
                zf.writestr(f"files/{r.id}_MISSING.txt", "The stored file could not be found.")
        zf.writestr(
            "README.txt",
            "JobPilot AI data export. data.json contains every record stored for your account "
            "(password and token hashes excluded). files/ contains uploaded resumes.",
        )
    return buf.getvalue()


async def delete_user(session: AsyncSession, user: User) -> dict[str, Any]:
    """Hard-delete every row and file keyed to the user, then verify nothing remains."""
    user_id = user.id
    resumes = (await session.execute(select(Resume).where(Resume.user_id == user_id))).scalars().all()
    for r in resumes:
        uploads.remove(r.storage_key)
    by_name = {m.__name__: m for m in USER_OWNED_MODELS}
    deleted: dict[str, int] = {}
    for name in DELETE_ORDER:
        model = by_name[name]
        res = await session.execute(delete(model).where(model.user_id == user_id))  # type: ignore[attr-defined]
        deleted[model.__tablename__] = int(res.rowcount or 0)
    await session.execute(delete(User).where(User.id == user_id))
    await session.flush()

    remaining: dict[str, int] = {}
    for model in USER_OWNED_MODELS:
        n = int(
            (
                await session.execute(
                    select(func.count()).select_from(model).where(model.user_id == user_id)  # type: ignore[attr-defined]
                )
            ).scalar_one()
        )
        if n:
            remaining[model.__tablename__] = n
    user_left = (await session.execute(select(func.count()).select_from(User).where(User.id == user_id))).scalar_one()
    files_left = [r.storage_key for r in resumes if (get_settings().upload_dir / f"{r.storage_key}.bin").exists()]
    verified = not remaining and not user_left and not files_left
    if not verified:
        raise RuntimeError("Hard deletion verification failed")
    return {"verified": True, "deleted_rows": deleted, "files_deleted": len(resumes)}
