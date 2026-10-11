"""Application schemas."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class ApplicationCreate(BaseModel):
    job_id: str
    status: str = "discovered"
    resume_version_id: Optional[str] = None
    cover_letter: Optional[str] = None
    notes: Optional[str] = None


class ApplicationStatusTransition(BaseModel):
    to_status: str
    message: Optional[str] = None
    activity_metadata: Dict[str, Any] = {}


class ApplicationActivityResponse(BaseModel):
    id: str
    application_id: str
    user_id: str
    from_status: Optional[str] = None
    to_status: str
    activity_type: str
    message: str
    activity_metadata: Dict[str, Any] = {}
    created_at: datetime

    class Config:
        from_attributes = True


class ApplicationResponse(BaseModel):
    id: str
    user_id: str
    job_id: str
    status: str
    resume_version_id: Optional[str] = None
    cover_letter: Optional[str] = None
    notes: Optional[str] = None
    applied_at: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    activities: List[ApplicationActivityResponse] = []

    class Config:
        from_attributes = True
