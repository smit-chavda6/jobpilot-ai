"""Job and JobMatch repository strictly scoped by user_id."""

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from apps.api.models.job import Job, JobMatch


class JobRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, user_id: str, job_id: str) -> Optional[Job]:
        stmt = (
            select(Job)
            .where(Job.id == job_id, Job.user_id == user_id)
            .options(selectinload(Job.matches))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_fingerprint(self, user_id: str, fingerprint: str) -> Optional[Job]:
        stmt = select(Job).where(Job.user_id == user_id, Job.job_fingerprint == fingerprint)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_jobs(
        self,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
        search: Optional[str] = None,
    ) -> List[Job]:
        stmt = (
            select(Job)
            .where(Job.user_id == user_id, Job.is_archived.is_(False))
            .options(selectinload(Job.matches))
            .order_by(Job.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if search:
            stmt = stmt.where((Job.title.ilike(f"%{search}%")) | (Job.company.ilike(f"%{search}%")))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, job: Job) -> Job:
        self.session.add(job)
        await self.session.flush()
        return job

    async def save_match(self, match: JobMatch) -> JobMatch:
        self.session.add(match)
        await self.session.flush()
        return match

    async def get_match(self, user_id: str, job_id: str) -> Optional[JobMatch]:
        stmt = select(JobMatch).where(JobMatch.user_id == user_id, JobMatch.job_id == job_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
