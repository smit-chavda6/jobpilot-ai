"""User Profile and Experience Pydantic schemas."""

from typing import List, Optional

from pydantic import BaseModel, Field


class EducationBase(BaseModel):
    institution: str = Field(min_length=1)
    degree: str = Field(min_length=1)
    field_of_study: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    gpa: Optional[str] = None


class EducationCreate(EducationBase):
    pass


class EducationResponse(EducationBase):
    id: str

    class Config:
        from_attributes = True


class ExperienceBase(BaseModel):
    company: str = Field(min_length=1)
    title: str = Field(min_length=1)
    location: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    is_current: bool = False
    description: Optional[str] = None


class ExperienceCreate(ExperienceBase):
    pass


class ExperienceResponse(ExperienceBase):
    id: str

    class Config:
        from_attributes = True


class ProjectBase(BaseModel):
    title: str = Field(min_length=1)
    description: Optional[str] = None
    url: Optional[str] = None
    technologies: List[str] = []


class ProjectCreate(ProjectBase):
    pass


class ProjectResponse(ProjectBase):
    id: str

    class Config:
        from_attributes = True


class SkillItem(BaseModel):
    name: str
    category: str = "technical"
    proficiency: int = Field(ge=1, le=5, default=3)
    verified: bool = False


class UserProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    headline: Optional[str] = None
    summary: Optional[str] = None
    location: Optional[str] = None
    phone: Optional[str] = None
    target_roles: Optional[List[str]] = None
    target_locations: Optional[List[str]] = None
    min_salary: Optional[int] = None
    remote_preference: Optional[str] = None
    work_authorization: Optional[str] = None


class UserProfileResponse(BaseModel):
    id: str
    user_id: str
    full_name: str
    headline: Optional[str] = None
    summary: Optional[str] = None
    location: Optional[str] = None
    phone: Optional[str] = None
    target_roles: List[str] = []
    target_locations: List[str] = []
    min_salary: Optional[int] = None
    remote_preference: str = "flexible"
    work_authorization: Optional[str] = None
    educations: List[EducationResponse] = []
    experiences: List[ExperienceResponse] = []
    projects: List[ProjectResponse] = []

    class Config:
        from_attributes = True
