from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import Role


class RegisterIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    # Optional: a Google-only student has no phone, and the watermark falls back
    # to the confirmed email address.
    phone: str | None = Field(default=None, pattern=r"^9\d{9}$")
    password: str = Field(min_length=8, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    email: EmailStr
    phone: str | None
    role: Role
    # The SPA shows a "confirm your email" banner from this instead of guessing.
    email_verified: bool


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class GoogleTokenOut(TokenOut):
    # False when the sign-in walked into an account that already existed. The
    # register page uses that to send the visitor to login instead of welcoming
    # them as new; login itself ignores the difference.
    created: bool


class RefreshIn(BaseModel):
    refresh_token: str = Field(min_length=20, max_length=200)


class GoogleLoginIn(BaseModel):
    # The credential Google Identity Services hands the button's callback.
    # It is JWT text, up to Google's 1 MB token ceiling in practice.
    id_token: str = Field(min_length=40, max_length=8192)
    # Read only when this sign-in creates the student, so a Gmail-only signup can
    # still be given a password to type later. An account that already exists
    # keeps the one it has.
    password: str | None = Field(default=None, min_length=8, max_length=128)


class VerifyEmailIn(BaseModel):
    token: str = Field(min_length=20, max_length=200)


class ResendVerificationIn(BaseModel):
    email: EmailStr