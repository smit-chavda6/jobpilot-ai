from __future__ import annotations

import re
from typing import Any, Literal

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.models import GeneratedDocument
from app.repositories import Repo
from app.routers._idem import idempotent
from app.security.deps import CurrentUser, SessionDep, check_if_match, etag_for, parse_uuid, rate_limit
from app.services import applications as app_service
from app.services import documents, profile_service

router = APIRouter(prefix="/api/documents", tags=["documents"])


class GenerateIn(BaseModel):
    kind: Literal["resume", "cover_letter"]
    job_id: str | None = None


class UpdateIn(BaseModel):
    items: list[dict[str, Any]] = Field(max_length=80)
    header: dict[str, str] | None = None


@router.get("")
async def list_documents(user: CurrentUser, session: SessionDep, job_id: str | None = None) -> list[dict[str, Any]]:
    where = [GeneratedDocument.job_id == parse_uuid(job_id)] if job_id else []
    rows = await Repo(session, GeneratedDocument, user.id).list(*where, order_by=GeneratedDocument.created_at.desc())
    return [{k: v for k, v in documents.doc_dict(d).items() if k not in ("content",)} for d in rows]


@router.post("", dependencies=[rate_limit("ai")])
async def generate(body: GenerateIn, request: Request, user: CurrentUser, session: SessionDep) -> JSONResponse:
    job_id = parse_uuid(body.job_id) if body.job_id else None

    async def run() -> dict[str, Any]:
        if body.kind == "resume":
            doc = await documents.generate_resume(session, user.id, user.email, job_id)
        else:
            doc = await documents.generate_cover_letter(session, user.id, user.email, job_id)
        return documents.doc_dict(doc)

    return await idempotent(request, session, user, "documents:generate", body.model_dump(), run)


@router.get("/{doc_id}")
async def get_document(doc_id: str, user: CurrentUser, session: SessionDep, response: Response) -> dict[str, Any]:
    doc = await Repo(session, GeneratedDocument, user.id).get(parse_uuid(doc_id))
    response.headers["ETag"] = etag_for(doc.version)
    facts = {str(f.id): f for f in await profile_service.confirmed_facts(session, user.id)}
    out = documents.doc_dict(doc)
    out["diff"] = documents.diff(doc, facts) if doc.kind == "resume" else []
    out["facts"] = [profile_service.fact_dict(f) for f in facts.values()]
    return out


@router.put("/{doc_id}")
async def update_document(
    doc_id: str, body: UpdateIn, request: Request, response: Response, user: CurrentUser, session: SessionDep
) -> dict[str, Any]:
    doc = await Repo(session, GeneratedDocument, user.id).get(parse_uuid(doc_id))
    check_if_match(request, doc.version)
    doc = await documents.update_document(session, user.id, doc, body.items, body.header)
    await session.flush()
    await app_service.on_document_changed(session, user.id, doc.id)
    response.headers["ETag"] = etag_for(doc.version)
    return documents.doc_dict(doc)


@router.delete("/{doc_id}", status_code=204)
async def delete_document(doc_id: str, user: CurrentUser, session: SessionDep) -> Response:
    repo = Repo(session, GeneratedDocument, user.id)
    doc = await repo.get(parse_uuid(doc_id))
    await repo.delete(doc)
    return Response(status_code=204)


@router.get("/{doc_id}/export")
async def export(
    doc_id: str, user: CurrentUser, session: SessionDep, format: Literal["pdf", "docx"] = "pdf"
) -> Response:
    doc = await Repo(session, GeneratedDocument, user.id).get(parse_uuid(doc_id))
    safe_title = re.sub(r"[^A-Za-z0-9_-]+", "_", doc.title)[:60] or "document"
    if format == "pdf":
        data, mime = documents.export_pdf(doc), "application/pdf"
    else:
        data = documents.export_docx(doc)
        mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return Response(
        data,
        media_type=mime,
        headers={"Content-Disposition": f'attachment; filename="{safe_title}.{format}"', "Cache-Control": "no-store"},
    )
