"""Profile Fact Pydantic schemas."""

from datetime import datetime
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field


class ProfileFactCreate(BaseModel):
    text: str = Field(min_length=3)
    category: str = "experience"
    source_type: Literal["resume", "manual", "import"] = "manual"
    source_id: Optional[str] = None
    entities: Dict[str, Any] = {}


class ProfileFactUpdate(BaseModel):
    text: Optional[str] = None
    category: Optional[str] = None
    confirmation_status: Optional[Literal["candidate", "confirmed", "rejected"]] = None
    entities: Optional[Dict[str, Any]] = None


class ProfileFactResponse(BaseModel):
    id: str
    user_id: str
    text: str
    category: str
    confirmation_status: str
    source_type: str
    source_id: Optional[str] = None
    entities: Dict[str, Any] = {}
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
