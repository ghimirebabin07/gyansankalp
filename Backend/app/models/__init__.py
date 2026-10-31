"""Importing this package registers every table on Base.metadata for Alembic."""

from app.models.user import User, Role
from app.models.admin import Admin
from app.models.refresh_token import RefreshToken
from app.models.course import Course, Topic
from app.models.enrollment import Enrollment, EnrollmentStatus
from app.models.material import Material, MaterialStatus
from app.models.access_log import AccessLog

__all__ = [
    "AccessLog",
    "Admin",
    "Course",
    "Enrollment",
    "EnrollmentStatus",
    "Material",
    "MaterialStatus",
    "RefreshToken",
    "Role",
    "Topic",
    "User",
]
