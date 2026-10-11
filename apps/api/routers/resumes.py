"""Resume upload, parsing, and management thin router."""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database import get_db_session
from apps.api.models.fact import ProfileFact
from apps.api.models.resume import Resume
from apps.api.models.user import User
from apps.api.security.dependencies import get_current_user
from apps.api.services.file_upload_service import validate_and_save_upload
from apps.api.services.resume_parser_service import parse_resume

router = APIRouter(prefix="/api/v1/resumes", tags=["Resumes"])


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
