from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class RegisterRequest(BaseModel):
    email: str = Field(
        min_length=3,
        max_length=320,
        pattern=EMAIL_PATTERN,
        description="User email, used as login",
    )
    password: str = Field(min_length=8, max_length=128, description="Plain password")


class LoginRequest(BaseModel):
    email: str = Field(
        min_length=3,
        max_length=320,
        pattern=EMAIL_PATTERN,
        description="User email",
    )
    password: str = Field(min_length=1, max_length=128, description="Plain password")


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    status: str
    role: str
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: UserResponse
