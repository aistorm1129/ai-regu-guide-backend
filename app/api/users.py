from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.schemas.user import UserResponse, UserUpdate
from app.api.deps import get_current_user, get_current_verified_user
from app.models.user import User
from app.models.organization import UserOrganization

router = APIRouter()


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get current user information"""
    
    # Get user's organization role
    result = await db.execute(
        select(UserOrganization).where(UserOrganization.user_id == current_user.id)
    )
    user_org = result.scalar_one_or_none()
    
    # Convert User model to dict and ensure plan is serialized as string
    user_data = {
        "id": current_user.id,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "plan": current_user.plan.value if current_user.plan else "basic",
        "is_active": current_user.is_active,
        "is_verified": current_user.is_verified,
        "is_superuser": current_user.is_superuser,
        "organization_role": user_org.role.value if user_org else "member",
        "created_at": current_user.created_at
    }
    return user_data


@router.patch("/me", response_model=UserResponse)
async def update_current_user(
    user_update: UserUpdate,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db)
):
    """Update current user information"""
    if user_update.email and user_update.email != current_user.email:
        # Check if new email is already taken
        from app.core.auth import get_user_by_email
        existing_user = await get_user_by_email(db, user_update.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
        current_user.email = user_update.email
        current_user.is_verified = False  # Require re-verification
    
    if user_update.full_name is not None:
        current_user.full_name = user_update.full_name
    
    await db.commit()
    await db.refresh(current_user)
    
    # Convert User model to dict and ensure plan is serialized as string
    user_data = {
        "id": current_user.id,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "plan": current_user.plan.value if current_user.plan else "basic",
        "is_active": current_user.is_active,
        "is_verified": current_user.is_verified,
        "created_at": current_user.created_at
    }
    return user_data


@router.delete("/me")
async def delete_current_user(
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete current user account"""
    await db.delete(current_user)
    await db.commit()
    
    return {"message": "User account deleted successfully"}