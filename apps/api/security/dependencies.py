"""Authentication and request security dependencies."""

from typing import Optional

from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database import get_db_session
from apps.api.models.user import User
from apps.api.repositories.user_repository import UserRepository
from apps.api.security.tokens import decode_token


async def get_current_user(
    request: Request,
    authorization: Optional[str] = Header(None),
    access_token_cookie: Optional[str] = Cookie(None, alias="access_token"),
    x_csrf_token: Optional[str] = Header(None),
    csrf_token_cookie: Optional[str] = Cookie(None, alias="csrf_token"),
    session: AsyncSession = Depends(get_db_session),
) -> User:
    """Authenticates the candidate via Authorization header or Secure HttpOnly cookie."""
    token = None
    using_cookie = False

    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
    elif access_token_cookie:
        token = access_token_cookie
        using_cookie = True

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please log in.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # If authenticating via cookie on state-changing request, enforce CSRF double-submit check
    if using_cookie and request.method in ["POST", "PUT", "PATCH", "DELETE"]:
        if not x_csrf_token or not csrf_token_cookie or x_csrf_token != csrf_token_cookie:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF token validation failed.",
            )

    try:
        payload = decode_token(token)
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication token payload.",
            )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired or is invalid.",
        )

    user_repo = UserRepository(session)
    user = await user_repo.get_by_id(user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found or has been disabled.",
        )

    # Attach user_id to request state for logging context
    request.state.user_id = user.id
    return user
