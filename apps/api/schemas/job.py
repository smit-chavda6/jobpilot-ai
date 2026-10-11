"""Job and matching schemas."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class JobCreate(BaseModel):
    title: str = Field(min_length=2)
    company: str = Field(min_length=1)
    location: Optional[str] = None
    remote_type: str = "on-site"
    employment_type: str = "full-time"
    description: str = Field(min_length=10)
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_currency: str = "USD"
    required_skills: List[str] = []
    preferred_skills: List[str] = []
    source_id: str = "manual_url"
    source_url: Optional[str] = None


class JobResponse(BaseModel):
    id: str
    user_id: str
    job_fingerprint: str
    title: str
    company: str
    location: Optional[str] = None
    remote_type: str
    employment_type: str
    description: str
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_currency: str
    required_skills: List[str] = []
    preferred_skills: List[str] = []
    source_id: str
    source_url: Optional[str] = None
    verification_status: str
    is_archived: bool
    created_at: datetime

    class Config:
        from_attributes = True


class JobMatchResponse(BaseModel):
    id: str
    user_id: str
    job_id: str
    score: float
    confidence: float
    hard_filter_passed: bool
    breakdown: Dict[str, Any]
    explanation: Dict[str, Any]
    created_at: datetime

    class Config:
        from_attributes = True
