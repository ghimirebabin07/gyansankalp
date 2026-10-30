from pydantic import BaseModel, ConfigDict, EmailStr


class AdminLoginIn(BaseModel):
    email: EmailStr
    password: str


class AdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str


class AdminTokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
