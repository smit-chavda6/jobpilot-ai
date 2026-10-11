"""Resume upload, tailoring, cover letters, grounding validation, and ATS export router."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database import get_db_session
from apps.api.models.fact import ProfileFact
from apps.api.models.resume import Resume, ResumeVersion
from apps.api.models.user import User
from apps.api.repositories.fact_repository import FactRepository
from apps.api.repositories.job_repository import JobRepository
from apps.api.repositories.resume_repository import ResumeRepository
from apps.api.security.dependencies import get_current_user
from apps.api.services.cover_letter_service import CoverLetterService
from apps.api.services.export_service import ExportService
from apps.api.services.file_upload_service import validate_and_save_upload
from apps.api.services.grounding_validator import GroundingValidator
from apps.api.services.resume_parser_service import parse_resume
from apps.api.services.resume_tailor_service import ResumeTailorService

router = APIRouter(prefix="/api/v1/resumes", tags=["Resumes"])


class TailorResumeRequest(BaseModel):
    target_job_id: str = Field(..., description="ID of job to tailor resume for")
    version_name: Optional[str] = Field(None, description="Custom label for version")


class CoverLetterRequest(BaseModel):
    target_job_id: str = Field(..., description="ID of job to generate cover letter for")


class ValidateGroundingRequest(BaseModel):
    claims: List[Dict[str, Any]] = Field(..., description="List of claim dictionaries with 'text' and 'cited_fact_ids'")


@router.post(
    "/upload",
    status_code=status.HTTP_201_CREATED,
    summary="Upload and parse resume into candidate ProfileFacts",
)
async def upload_resume(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    # 1. Validate magic bytes, MIME, and size caps
    stored_path, original_filename, file_size, mime_type = await validate_and_save_upload(file)

    # 2. Extract text and parse into candidate facts
    try:
        raw_text, parsed_data, candidate_facts = parse_resume(stored_path, mime_type)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to parse resume document content: {str(e)}",
        )

    # 3. Create Resume record
    resume = Resume(
        user_id=current_user.id,
        filename=original_filename,
        file_path=stored_path,
        file_size=file_size,
        mime_type=mime_type,
        raw_text=raw_text,
        parsed_data=parsed_data,
        is_primary=True,
    )
    session.add(resume)
    await session.flush()

    # 4. Decompose and store candidate ProfileFacts (unusable until confirmed)
    created_fact_ids = []
    for fact_data in candidate_facts:
        fact = ProfileFact(
            user_id=current_user.id,
            text=fact_data["text"],
            category=fact_data["category"],
            confirmation_status="candidate",
            source_type="resume",
            source_id=resume.id,
            entities=fact_data["entities"],
        )
        session.add(fact)
        created_fact_ids.append(fact.id)

    await session.flush()

    return {
        "resume_id": resume.id,
        "filename": original_filename,
        "file_size": file_size,
        "mime_type": mime_type,
        "parsed_skills": parsed_data.get("skills", []),
        "candidate_facts_count": len(candidate_facts),
        "message": "Resume uploaded successfully. Generated candidate facts require user confirmation before downstream use.",
    }


@router.get("", summary="List candidate uploaded resumes")
async def list_resumes(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    stmt = (
        select(Resume).where(Resume.user_id == current_user.id).order_by(Resume.created_at.desc())
    )
    result = await session.execute(stmt)
    resumes = result.scalars().all()
    return [
        {
            "id": r.id,
            "filename": r.filename,
            "file_size": r.file_size,
            "mime_type": r.mime_type,
            "is_primary": r.is_primary,
            "created_at": r.created_at,
        }
        for r in resumes
    ]


@router.post(
    "/{resume_id}/tailor",
    status_code=status.HTTP_201_CREATED,
    summary="Tailor resume against a target job with diff view and grounding validation",
)
async def tailor_resume(
    resume_id: str,
    req: TailorResumeRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    resume_repo = ResumeRepository(session)
    job_repo = JobRepository(session)
    fact_repo = FactRepository(session)

    resume = await resume_repo.get_resume_by_id(current_user.id, resume_id)
    if not resume:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found")

    job = await job_repo.get_by_id(current_user.id, req.target_job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target job not found")

    confirmed_facts = await fact_repo.list_by_user(current_user.id, confirmation_status="confirmed")
    if not confirmed_facts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot tailor resume: Candidate has zero confirmed ProfileFacts. Confirm profile facts first.",
        )

    cand_name = current_user.email.split("@")[0].title()
    service = ResumeTailorService()
    tailored_result = service.tailor_resume(
        resume=resume,
        job=job,
        confirmed_facts=confirmed_facts,
        candidate_name=cand_name,
        candidate_email=current_user.email,
    )

    version_name = req.version_name or f"Tailored for {job.company} - {job.title}"
    resume_version = ResumeVersion(
        user_id=current_user.id,
        resume_id=resume.id,
        target_job_id=job.id,
        version_name=version_name,
        tailored_content=tailored_result["tailored_content"],
        cited_fact_ids=tailored_result["cited_fact_ids"],
        grounding_score=tailored_result["grounding_score"],
        is_approved=tailored_result["is_valid"],
    )
    await resume_repo.create_version(resume_version)

    return {
        "version_id": resume_version.id,
        "resume_id": resume.id,
        "target_job_id": job.id,
        "version_name": version_name,
        "grounding_score": tailored_result["grounding_score"],
        "is_grounded": tailored_result["is_valid"],
        "violations": tailored_result["violations"],
        "diff": tailored_result["diff"],
        "tailored_content": tailored_result["tailored_content"],
    }


@router.get("/{resume_id}/versions", summary="List tailored versions of a resume")
async def list_resume_versions(
    resume_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    resume_repo = ResumeRepository(session)
    resume = await resume_repo.get_resume_by_id(current_user.id, resume_id)
    if not resume:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found")

    versions = await resume_repo.list_versions_by_resume(current_user.id, resume_id)
    return [
        {
            "id": v.id,
            "version_name": v.version_name,
            "target_job_id": v.target_job_id,
            "grounding_score": v.grounding_score,
            "is_approved": v.is_approved,
            "created_at": v.created_at,
        }
        for v in versions
    ]


@router.post(
    "/cover-letter",
    summary="Generate 3-paragraph grounded cover letter strictly citing confirmed facts",
)
async def generate_cover_letter(
    req: CoverLetterRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    job_repo = JobRepository(session)
    fact_repo = FactRepository(session)

    job = await job_repo.get_by_id(current_user.id, req.target_job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target job not found")

    confirmed_facts = await fact_repo.list_by_user(current_user.id, confirmation_status="confirmed")
    if not confirmed_facts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot generate cover letter: Candidate has zero confirmed ProfileFacts.",
        )

    cand_name = current_user.email.split("@")[0].title()
    service = CoverLetterService()
    letter = service.generate_grounded_letter(
        candidate_name=cand_name,
        job=job,
        confirmed_facts=confirmed_facts,
    )
    return letter


@router.post(
    "/validate-grounding",
    summary="Deterministic grounding validator for claims citing profile facts",
)
async def validate_grounding(
    req: ValidateGroundingRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    fact_repo = FactRepository(session)
    confirmed_facts = await fact_repo.list_by_user(current_user.id, confirmation_status="confirmed")
    validator = GroundingValidator(confirmed_facts)
    result = validator.validate_content(req.claims)
    return result.to_dict()


@router.get(
    "/versions/{version_id}/export/pdf",
    summary="Export ATS-compliant single-column PDF resume",
)
async def export_resume_pdf(
    version_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    resume_repo = ResumeRepository(session)
    version = await resume_repo.get_version_by_id(current_user.id, version_id)
    if not version:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume version not found")

    pdf_bytes = ExportService.generate_pdf(version.tailored_content)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="resume_{version_id}.pdf"'},
    )


@router.get(
    "/versions/{version_id}/export/docx",
    summary="Export ATS-compliant single-column DOCX resume",
)
async def export_resume_docx(
    version_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    resume_repo = ResumeRepository(session)
    version = await resume_repo.get_version_by_id(current_user.id, version_id)
    if not version:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume version not found")

    docx_bytes = ExportService.generate_docx(version.tailored_content)
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="resume_{version_id}.docx"'},
    )
