from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

SLUG = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"


class TopicOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    position: int


class CourseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    slug: str
    description: str
    syllabus: str
    exam_level: str
    price_npr: int


class CourseDetail(CourseOut):
    topics: list[TopicOut]


class CourseAdminOut(CourseOut):
    is_published: bool
    created_at: datetime


class CourseCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    slug: str = Field(max_length=120, pattern=SLUG)
    description: str = Field("", max_length=4000)
    syllabus: str = Field("", max_length=20000)
    # the column is varchar(50); a longer value used to fail in the database
    exam_level: str = Field("", max_length=50)
    price_npr: int = Field(0, ge=0, le=10_000_000)
    is_published: bool = False


class CourseUpdate(BaseModel):
    title: str | None = Field(None, min_length=3, max_length=200)
    slug: str | None = Field(None, max_length=120, pattern=SLUG)
    description: str | None = Field(None, max_length=4000)
    syllabus: str | None = Field(None, max_length=20000)
    exam_level: str | None = Field(None, max_length=50)
    price_npr: int | None = Field(None, ge=0, le=10_000_000)
    is_published: bool | None = None


class TopicCreate(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    position: int = Field(0, ge=0)


class TopicUpdate(BaseModel):
    title: str | None = Field(None, min_length=2, max_length=200)
    position: int | None = Field(None, ge=0)
