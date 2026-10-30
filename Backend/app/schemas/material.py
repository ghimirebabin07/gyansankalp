from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.material import MaterialStatus


class MaterialPublic(BaseModel):
    """What a student sees."""
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    page_count: int | None
    # set by the topic materials endpoint so the student view can show context
    topic_title: str = ""


class MaterialOut(BaseModel):
    """What an admin sees."""
    model_config = ConfigDict(from_attributes=True)
    id: int
    topic_id: int
    title: str
    size_bytes: int
    page_count: int | None
    status: MaterialStatus
    error: str | None
    attempts: int
    created_at: datetime


class MaterialUpdate(BaseModel):
    title: str = Field(min_length=2, max_length=200)
