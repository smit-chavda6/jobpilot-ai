"""Authentication thin router handling registration, login, cookies, and session state."""

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import settings
from apps.api.database import get_db_session
from apps.api.models.user import User
from apps.api.schemas.auth import (
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)
from apps.api.security.dependencies import get_current_user
from apps.api.services.auth_service import AuthService

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])


def _set_auth_cookies(
    response: Response, access_token: str, refresh_token: str, csrf_token: str
) -> None:
    is_secure = settings.ENVIRONMENT == "production"
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=is_secure,
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=is_secure,
        samesite="lax",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
    )
    response.set_cookie(
        key="csrf_token",
        value=csrf_token,
        httponly=False,  # Accessible to JS client for double-submit header
        secure=is_secure,
        samesite="lax",
    )


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register new candidate account",
)
async def register(
    payload: UserRegisterRequest,
    response: Response,
    session: AsyncSession = Depends(get_db_session),
):
    service = AuthService(session)
    token_response, refresh_token = await service.register(payload)
    _set_auth_cookies(
        response,
        token_response.access_token,
        refresh_token,
        token_response.csrf_token,
    )
    return token_response


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate candidate credentials",
)
async def login(
    payload: UserLoginRequest,
    response: Response,
    session: AsyncSession = Depends(get_db_session),
):
    service = AuthService(session)
    token_response, refresh_token = await service.login(payload)
    _set_auth_cookies(
        response,
        token_response.access_token,
        refresh_token,
        token_response.csrf_token,
    )
    return token_response


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    summary="Log out candidate and clear session cookies",
)
async def logout(response: Response):
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    response.delete_cookie("csrf_token")
    return {"message": "Successfully logged out."}


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Retrieve authenticated candidate identity",
)
async def get_me(current_user: User = Depends(get_current_user)):
    return UserResponse.model_validate(current_user)
