from fastapi import APIRouter, Depends, status

from app.api.deps import get_auth_service
from app.api.v1.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from app.api.v1.schemas.error import ErrorResponse
from app.services.auth_service import AuthService

router = APIRouter()

ERROR_RESPONSES = {
    401: {"model": ErrorResponse, "description": "Invalid credentials"},
    409: {"model": ErrorResponse, "description": "Email already exists"},
    422: {"model": ErrorResponse, "description": "Validation error"},
}


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register user",
    description="Creates a user account and returns a JWT access token.",
    responses=ERROR_RESPONSES,
)
async def register(
    payload: RegisterRequest,
    service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    user, token, expires_at = await service.register(payload)
    return TokenResponse(
        access_token=token,
        expires_at=expires_at,
        user=UserResponse.model_validate(user),
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login user",
    description="Authenticates user by email and password and returns a JWT access token.",
    responses=ERROR_RESPONSES,
)
async def login(
    payload: LoginRequest,
    service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    user, token, expires_at = await service.login(payload)
    return TokenResponse(
        access_token=token,
        expires_at=expires_at,
        user=UserResponse.model_validate(user),
    )
