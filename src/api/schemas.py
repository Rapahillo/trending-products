from pydantic import BaseModel, EmailStr


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: str
    email: str
    subscription_tier: str
    region_preference: str | None
    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ApiResponse(BaseModel):
    status: str = "ok"
    data: dict | list | None = None
    meta: dict | None = None


class ErrorResponse(BaseModel):
    status: str = "error"
    error: dict
