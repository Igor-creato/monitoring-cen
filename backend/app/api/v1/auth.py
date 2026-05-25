from fastapi import APIRouter, Depends, Response, status

from app.api.deps import get_auth_service
from app.api.v1.schemas.auth import (
    LoginRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    PasswordResetRequestResponse,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
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


@router.post(
    "/password-reset/request",
    response_model=PasswordResetRequestResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Request password reset",
    description="Sends a password reset email when the account exists.",
    responses={422: {"model": ErrorResponse, "description": "Validation error"}},
)
async def request_password_reset(
    payload: PasswordResetRequest,
    service: AuthService = Depends(get_auth_service),
) -> PasswordResetRequestResponse:
    await service.request_password_reset(payload.email)
    return PasswordResetRequestResponse(
        message="If this email is registered, password reset instructions will be sent.",
    )


@router.post(
    "/password-reset/confirm",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Confirm password reset",
    description="Sets a new password using a valid one-time reset token.",
    responses={
        401: {"model": ErrorResponse, "description": "Invalid reset token"},
        **ERROR_RESPONSES,
    },
)
async def confirm_password_reset(
    payload: PasswordResetConfirmRequest,
    service: AuthService = Depends(get_auth_service),
) -> Response:
    await service.confirm_password_reset(payload.token, payload.password)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
