"""Resume and ResumeVersion repository with strict user_id tenant isolation."""

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models.resume import Resume, ResumeVersion


class ResumeRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_resume_by_id(self, user_id: str, resume_id: str) -> Optional[Resume]:
        stmt = select(Resume).where(Resume.id == resume_id, Resume.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_primary_resume(self, user_id: str) -> Optional[Resume]:
        stmt = (
            select(Resume)
            .where(Resume.user_id == user_id, Resume.is_primary == True)  # noqa: E712
            .order_by(Resume.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def list_resumes_by_user(self, user_id: str) -> List[Resume]:
        stmt = select(Resume).where(Resume.user_id == user_id).order_by(Resume.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create_version(self, version: ResumeVersion) -> ResumeVersion:
        self.session.add(version)
        await self.session.flush()
        return version

    async def get_version_by_id(self, user_id: str, version_id: str) -> Optional[ResumeVersion]:
        stmt = select(ResumeVersion).where(
            ResumeVersion.id == version_id, ResumeVersion.user_id == user_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_versions_by_resume(self, user_id: str, resume_id: str) -> List[ResumeVersion]:
        stmt = (
            select(ResumeVersion)
            .where(ResumeVersion.user_id == user_id, ResumeVersion.resume_id == resume_id)
            .order_by(ResumeVersion.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
