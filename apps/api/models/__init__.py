"""Database models package."""

from apps.api.models.application import (
    Application,
    ApplicationActivity,
    ApplicationDocument,
    ScreeningAnswer,
)
from apps.api.models.fact import ProfileFact
from apps.api.models.interaction import (
    AIUsageLog,
    Interview,
    Notification,
    RecruiterContact,
    Reminder,
    UserIntegration,
)
from apps.api.models.job import Job, JobEmbedding, JobMatch, JobSource
from apps.api.models.profile import (
    Education,
    Experience,
    Project,
    Skill,
    UserProfile,
    UserSkill,
)
from apps.api.models.resume import Resume, ResumeVersion
from apps.api.models.security import ApprovalRecord, AuditLog, ConsentRecord
from apps.api.models.user import User

__all__ = [
    "User",
    "UserProfile",
    "Education",
    "Experience",
    "Project",
    "Skill",
    "UserSkill",
    "ProfileFact",
    "Resume",
    "ResumeVersion",
    "JobSource",
    "Job",
    "JobEmbedding",
    "JobMatch",
    "Application",
    "ApplicationDocument",
    "ApplicationActivity",
    "ScreeningAnswer",
    "RecruiterContact",
    "Interview",
    "Reminder",
    "Notification",
    "AIUsageLog",
    "UserIntegration",
    "ApprovalRecord",
    "AuditLog",
    "ConsentRecord",
]
