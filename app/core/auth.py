from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.user import User, OAuthAccount
from app.core.security import verify_password, get_password_hash
import uuid


async def authenticate_user(db: AsyncSession, email: str, password: str) -> Optional[User]:
    """Authenticate user with email and password"""
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    
    if not user or not user.hashed_password:
        return None
    
    if not verify_password(password, user.hashed_password):
        return None
    
    return user


async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    """Get user by email"""
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> Optional[User]:
    """Get user by ID"""
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def create_user(
    db: AsyncSession,
    email: str,
    password: Optional[str] = None,
    full_name: Optional[str] = None,
    is_verified: bool = False,
    plan: str = "basic"
) -> User:
    """Create new user"""
    print(f"DEBUG create_user: Starting user creation for {email}")
    
    from app.models.user import PlanType
    plan_enum = PlanType.BASIC if plan == "basic" else PlanType.PROFESSIONAL
    
    user = User(
        email=email,
        hashed_password=get_password_hash(password) if password else None,
        full_name=full_name,
        is_verified=is_verified,
        is_active=True,
        plan=plan_enum
    )
    print(f"DEBUG create_user: User object created: {user.email} with plan: {plan}")
    
    db.add(user)
    print(f"DEBUG create_user: User added to session")
    
    await db.flush()
    print(f"DEBUG create_user: Session flushed")
    
    await db.refresh(user)
    print(f"DEBUG create_user: User refreshed, ID: {user.id}")
    
    return user


async def get_or_create_oauth_user(
    db: AsyncSession,
    email: str,
    oauth_name: str,
    oauth_id: str,
    full_name: Optional[str] = None,
    access_token: Optional[str] = None
) -> User:
    """Get or create user from OAuth provider"""
    # Check if user exists
    user = await get_user_by_email(db, email)
    
    if not user:
        # Create new user
        user = await create_user(
            db=db,
            email=email,
            full_name=full_name,
            is_verified=True  # OAuth users are pre-verified
        )
    
    # Check if OAuth account exists
    result = await db.execute(
        select(OAuthAccount).where(
            OAuthAccount.user_id == user.id,
            OAuthAccount.oauth_name == oauth_name
        )
    )
    oauth_account = result.scalar_one_or_none()
    
    if not oauth_account:
        # Create OAuth account link
        oauth_account = OAuthAccount(
            user_id=user.id,
            oauth_name=oauth_name,
            oauth_id=oauth_id,
            access_token=access_token
        )
        db.add(oauth_account)
    else:
        # Update access token
        oauth_account.access_token = access_token
    
    await db.flush()
    await db.refresh(user)
    
    return user


async def update_user_password(db: AsyncSession, user: User, new_password: str) -> User:
    """Update user password"""
    user.hashed_password = get_password_hash(new_password)
    await db.flush()
    await db.refresh(user)
    return user