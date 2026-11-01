from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.admin import AdminRole


class AdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str
    role: AdminRole
    is_active: bool
    # The panel can say "this account has not signed in with Google yet" from this
    # instead of guessing, which is the difference between a staff member being
    # added and being able to use the account.
    google_linked: bool
    created_at: datetime


class AdminTokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class OtpChallengeOut(BaseModel):
    """What the browser gets between the two halves of staff login.

    The code is never in here - this carries the waiting-room pass and the numbers
    the countdown on screen is built from.
    """

    challenge: str
    code_expires_in: int
    resend_after: int


class OtpVerifyIn(BaseModel):
    challenge: str = Field(min_length=20, max_length=8192)
    code: str = Field(pattern=r"^\d{6}$")


class OtpResendIn(BaseModel):
    challenge: str = Field(min_length=20, max_length=8192)


class StaffCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    # Has to be the address their Google account is verified on: sign-in compares
    # Google's word about the address against this row.
    email: EmailStr
    role: AdminRole


class StaffUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    email: EmailStr | None = None
    role: AdminRole | None = None
    is_active: bool | None = None


class StaffCoursesIn(BaseModel):
    """The whole set of courses an editor may touch, not one row at a time.

    Replacing the list keeps "this editor works on these three courses" expressible
    in a single call, so an accidental extra course cannot survive a relist.
    """

    course_ids: list[int] = Field(default_factory=list, max_length=200)


class StaffActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    admin_id: int | None
    action: str
    target: str | None
    created_at: datetime
