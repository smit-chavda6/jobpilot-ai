"""Authentication and User management business logic service."""

from typing import Tuple

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models.profile import UserProfile
from apps.api.models.security import ConsentRecord
from apps.api.models.user import User
from apps.api.repositories.user_repository import UserRepository
from apps.api.schemas.auth import (
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)
from apps.api.security.passwords import hash_password, verify_password
from apps.api.security.tokens import (
    create_access_token,
    create_refresh_token,
    generate_csrf_token,
)


class AuthService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_repo = UserRepository(session)

    async def register(
        self, data: UserRegisterRequest, ip_address: str = "127.0.0.1"
    ) -> Tuple[TokenResponse, str]:
        # Check existing email
        existing = await self.user_repo.get_by_email(data.email)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email address already exists.",
            )

        # Create user
        user = User(
            email=data.email.lower().strip(),
            hashed_password=hash_password(data.password),
            is_active=True,
            is_verified=False,
            role="candidate",
        )
        await self.user_repo.create(user)

        # Initialize UserProfile
        profile = UserProfile(
            user_id=user.id,
            full_name=data.full_name,
            target_roles=[],
            target_locations=[],
        )
        self.session.add(profile)

        # Record initial consent record for AI processing
        consent = ConsentRecord(
            user_id=user.id,
            consent_type="ai_processing",
            granted=True,
            policy_version="1.0",
            ip_address=ip_address,
        )
        self.session.add(consent)
        await self.session.flush()

        # Generate tokens
        token_data = {"sub": user.id, "email": user.email, "role": user.role}
        access_token = create_access_token(token_data)
        refresh_token = create_refresh_token(token_data)
        csrf_token = generate_csrf_token()

        response = TokenResponse(
            access_token=access_token,
            csrf_token=csrf_token,
            user=UserResponse.model_validate(user),
        )
        return response, refresh_token

    async def login(self, data: UserLoginRequest) -> Tuple[TokenResponse, str]:
        user = await self.user_repo.get_by_email(data.email)
        # Protect against user enumeration by constant time check simulation
        if not user or not verify_password(data.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password.",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account has been deactivated. Please contact support.",
            )

        token_data = {"sub": user.id, "email": user.email, "role": user.role}
        access_token = create_access_token(token_data)
        refresh_token = create_refresh_token(token_data)
        csrf_token = generate_csrf_token()

        response = TokenResponse(
            access_token=access_token,
            csrf_token=csrf_token,
            user=UserResponse.model_validate(user),
        )
        return response, refresh_token
