"""Job ingestion and listing router with SSRF protection and dedup."""

from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.adapters.base import JobDraft
from apps.api.adapters.email_import import parse_eml_job_alert
from apps.api.adapters.file_import import parse_csv_jobs, parse_json_jobs
from apps.api.adapters.greenhouse import GreenhouseAdapter
from apps.api.database import get_db_session
from apps.api.models.user import User
from apps.api.repositories.job_repository import JobRepository
from apps.api.schemas.job import JobResponse
from apps.api.security.dependencies import get_current_user
from apps.api.services.job_ingestion_service import JobIngestionService, sanitize_job_description
from apps.api.services.resume_parser_service import extract_skills_from_text
from apps.api.services.ssrf_protector import fetch_url_safely

router = APIRouter(prefix="/api/v1/jobs", tags=["Jobs"])


class UrlImportRequest(BaseModel):
    url: str
    company: Optional[str] = None
    title: Optional[str] = None


class GreenhouseImportRequest(BaseModel):
    board_token: str


@router.get("", response_model=List[JobResponse], summary="List ingested jobs")
async def list_jobs(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    search: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    repo = JobRepository(session)
    jobs = await repo.list_jobs(current_user.id, limit=limit, offset=offset, search=search)
    return [JobResponse.model_validate(j) for j in jobs]


@router.get("/{job_id}", response_model=JobResponse, summary="Get job detail")
async def get_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    repo = JobRepository(session)
    job = await repo.get_by_id(current_user.id, job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found or access denied.",
        )
    return JobResponse.model_validate(job)


@router.post(
    "/import/url",
    response_model=JobResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Import job from external URL with SSRF validation",
)
async def import_job_from_url(
    payload: UrlImportRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    # 1. SSRF DNS validation and safe HTTP fetch
    html_content = await fetch_url_safely(payload.url)
    clean_text = sanitize_job_description(html_content)

    title = payload.title or clean_text.split("\n")[0][:100] or "Imported Job"
    company = payload.company or "External Employer"
    skills = extract_skills_from_text(clean_text)

    draft = JobDraft(
        title=title,
        company=company,
        description=clean_text,
        location="Remote",
        remote_type="remote",
        employment_type="full-time",
        required_skills=skills[:6],
        preferred_skills=skills[6:10],
        source_id="manual_url",
        source_url=payload.url,
    )

    ingestion = JobIngestionService(session)
    job, is_new = await ingestion.ingest_job_draft(current_user.id, draft)
    return JobResponse.model_validate(job)


@router.post(
    "/import/greenhouse",
    response_model=List[JobResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Import live listings from Greenhouse public ATS board",
)
async def import_from_greenhouse(
    payload: GreenhouseImportRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    adapter = GreenhouseAdapter()
    ingestion = JobIngestionService(session)

    imported_jobs = []
    async for raw_job in adapter.fetch({"board_token": payload.board_token}):
        draft = adapter.normalize(raw_job)
        job, is_new = await ingestion.ingest_job_draft(current_user.id, draft)
        imported_jobs.append(job)

    return [JobResponse.model_validate(j) for j in imported_jobs]


@router.post(
    "/import/file",
    response_model=List[JobResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Import jobs from uploaded CSV, JSON, or .eml alert file",
)
async def import_from_file(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    content_bytes = await file.read()
    filename = (file.filename or "").lower()

    drafts: List[JobDraft] = []
    if filename.endswith(".json"):
        text = content_bytes.decode("utf-8")
        drafts = parse_json_jobs(text)
    elif filename.endswith(".csv"):
        text = content_bytes.decode("utf-8")
        drafts = parse_csv_jobs(text)
    elif filename.endswith(".eml") or filename.endswith(".msg"):
        drafts = parse_eml_job_alert(content_bytes)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file format. Please upload a .json, .csv, or .eml file.",
        )

    ingestion = JobIngestionService(session)
    result_jobs = []
    for draft in drafts:
        job, is_new = await ingestion.ingest_job_draft(current_user.id, draft)
        result_jobs.append(job)

    return [JobResponse.model_validate(j) for j in result_jobs]
