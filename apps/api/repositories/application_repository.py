"""Application repository strictly enforcing user_id scoping."""

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from apps.api.models.application import (
    Application,
    ApplicationActivity,
    ScreeningAnswer,
)


class ApplicationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, user_id: str, app_id: str) -> Optional[Application]:
        stmt = (
            select(Application)
            .where(Application.id == app_id, Application.user_id == user_id)
            .options(
                selectinload(Application.activities),
                selectinload(Application.job),
                selectinload(Application.screening_answers),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_job_id(self, user_id: str, job_id: str) -> Optional[Application]:
        stmt = select(Application).where(
            Application.user_id == user_id, Application.job_id == job_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_user(self, user_id: str, status: Optional[str] = None) -> List[Application]:
        stmt = (
            select(Application)
            .where(Application.user_id == user_id)
            .options(
                selectinload(Application.activities),
                selectinload(Application.job),
            )
            .order_by(Application.updated_at.desc())
        )
        if status:
            stmt = stmt.where(Application.status == status)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, app: Application) -> Application:
        self.session.add(app)
        await self.session.flush()
        return app

    async def add_activity(self, activity: ApplicationActivity) -> ApplicationActivity:
        self.session.add(activity)
        await self.session.flush()
        return activity

    async def add_screening_answer(self, answer: ScreeningAnswer) -> ScreeningAnswer:
        self.session.add(answer)
        await self.session.flush()
        return answer
