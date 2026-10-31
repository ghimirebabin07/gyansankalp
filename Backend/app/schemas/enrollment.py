from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enrollment import EnrollmentStatus


class EnrollmentGrant(BaseModel):
    email: EmailStr
    course_id: int = Field(gt=0)
    days: int | None = Field(None, ge=1, le=3650)  # None = lifetime


class EnrollmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    course_id: int
    status: EnrollmentStatus
    starts_at: datetime
    expires_at: datetime | None
