from pydantic import BaseModel, ConfigDict, EmailStr, Field


class AdminLoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=1024)


class AdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str


class AdminTokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
