from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, update
from sqlalchemy.orm import selectinload
from app.database import get_db
from app.api.deps import get_current_user, get_current_verified_user, get_user_organization, get_current_superuser
from app.models.user import User
from app.models.organization import Organization, UserOrganization, OrganizationSize
from app.models.jurisdiction import Jurisdiction, OrganizationJurisdiction
from typing import List, Optional
from uuid import UUID
from datetime import datetime
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/current")
async def get_current_organization(
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization),
    db: AsyncSession = Depends(get_db)
):
    """Get current user's organization details"""
    
    # Get user's role in organization
    role_result = await db.execute(
        select(UserOrganization.role).where(
            and_(
                UserOrganization.user_id == current_user.id,
                UserOrganization.organization_id == organization.id
            )
        )
    )
    user_role = role_result.scalar_one_or_none()
    
    # Get organization jurisdictions
    jurisdictions_result = await db.execute(
        select(Jurisdiction).join(OrganizationJurisdiction).where(
            OrganizationJurisdiction.organization_id == organization.id
        )
    )
    jurisdictions = []
    for jurisdiction in jurisdictions_result.scalars():
        jurisdictions.append({
            "id": str(jurisdiction.id),
            "name": jurisdiction.name,
            "code": jurisdiction.regulation_type.value,  # Use regulation_type as code
            "description": jurisdiction.description,
            "regulation_type": jurisdiction.regulation_type
        })
    
    # Get member count
    member_count_result = await db.execute(
        select(func.count(UserOrganization.user_id)).where(
            UserOrganization.organization_id == organization.id
        )
    )
    member_count = member_count_result.scalar() or 0
    
    return {
        "id": str(organization.id),
        "name": organization.name,
        "description": organization.description,
        "industry": organization.industry,
        "size": organization.size.value if organization.size else None,
        "country": organization.country,
        "created_at": organization.created_at.isoformat(),
        "updated_at": organization.updated_at.isoformat() if organization.updated_at else None,
        "user_role": user_role.value if user_role else None,
        "member_count": member_count,
        "jurisdictions": jurisdictions
    }


@router.put("/current")
async def update_current_organization(
    org_data: dict,
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization),
    db: AsyncSession = Depends(get_db)
):
    """Update current organization details"""
    
    # Check if user has admin role
    role_result = await db.execute(
        select(UserOrganization.role).where(
            and_(
                UserOrganization.user_id == current_user.id,
                UserOrganization.organization_id == organization.id
            )
        )
    )
    user_role = role_result.scalar_one_or_none()
    
    if user_role != "ADMIN":
        raise HTTPException(
            status_code=403, 
            detail="Only organization administrators can update organization details"
        )
    
    # Update fields
    update_fields = {}
    
    if "name" in org_data:
        update_fields["name"] = org_data["name"]
    
    if "description" in org_data:
        update_fields["description"] = org_data["description"]
    
    if "industry" in org_data:
        update_fields["industry"] = org_data["industry"]
    
    if "size" in org_data:
        try:
            update_fields["size"] = OrganizationSize(org_data["size"])
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid organization size: {org_data['size']}")
    
    if "country" in org_data:
        update_fields["country"] = org_data["country"]
    
    # website and settings fields removed - not present in Organization model
    
    if update_fields:
        update_fields["updated_at"] = datetime.utcnow()
        
        await db.execute(
            update(Organization).where(
                Organization.id == organization.id
            ).values(**update_fields)
        )
        await db.commit()
    
    return {"message": "Organization updated successfully"}


@router.get("/members")
async def get_organization_members(
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization),
    db: AsyncSession = Depends(get_db)
):
    """Get organization members"""
    
    # Get all members with their roles
    members_result = await db.execute(
        select(User, UserOrganization.role).join(UserOrganization).where(
            UserOrganization.organization_id == organization.id
        )
    )
    
    members = []
    for user, role in members_result:
        members.append({
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "is_active": user.is_active,
            "is_verified": user.is_verified,
            "role": role,
            "joined_at": user.created_at.isoformat()
        })
    
    return {
        "members": members,
        "total_members": len(members)
    }


@router.post("/invite")
async def invite_user_to_organization(
    invitation_data: dict,
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization),
    db: AsyncSession = Depends(get_db)
):
    """Invite a user to join the organization"""
    
    # Check if user has admin role
    role_result = await db.execute(
        select(UserOrganization.role).where(
            and_(
                UserOrganization.user_id == current_user.id,
                UserOrganization.organization_id == organization.id
            )
        )
    )
    user_role = role_result.scalar_one_or_none()
    
    if user_role != "ADMIN":
        raise HTTPException(
            status_code=403, 
            detail="Only organization administrators can invite users"
        )
    
    if "email" not in invitation_data:
        raise HTTPException(status_code=400, detail="Email is required")
    
    # Check if user already exists
    user_result = await db.execute(
        select(User).where(User.email == invitation_data["email"])
    )
    user = user_result.scalar_one_or_none()
    
    if not user:
        return {
            "message": f"User with email {invitation_data['email']} not found. They need to sign up first.",
            "status": "user_not_found"
        }
    
    # Check if user is already in organization
    existing_member = await db.execute(
        select(UserOrganization).where(
            and_(
                UserOrganization.user_id == user.id,
                UserOrganization.organization_id == organization.id
            )
        )
    )
    
    if existing_member.scalar_one_or_none():
        raise HTTPException(
            status_code=400, 
            detail="User is already a member of this organization"
        )
    
    # Add user to organization
    user_org = UserOrganization(
        user_id=user.id,
        organization_id=organization.id,
        role=invitation_data.get("role", "MEMBER")
    )
    
    db.add(user_org)
    await db.commit()
    
    return {
        "message": f"User {user.email} has been added to the organization",
        "user_id": str(user.id),
        "role": invitation_data.get("role", "MEMBER")
    }


@router.delete("/members/{user_id}")
async def remove_organization_member(
    user_id: UUID,
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization),
    db: AsyncSession = Depends(get_db)
):
    """Remove a member from the organization"""
    
    # Check if current user has admin role
    role_result = await db.execute(
        select(UserOrganization.role).where(
            and_(
                UserOrganization.user_id == current_user.id,
                UserOrganization.organization_id == organization.id
            )
        )
    )
    user_role = role_result.scalar_one_or_none()
    
    if user_role != "ADMIN":
        raise HTTPException(
            status_code=403, 
            detail="Only organization administrators can remove members"
        )
    
    # Prevent removing self
    if user_id == current_user.id:
        raise HTTPException(
            status_code=400, 
            detail="Cannot remove yourself from the organization"
        )
    
    # Find the user organization relationship
    user_org_result = await db.execute(
        select(UserOrganization).where(
            and_(
                UserOrganization.user_id == user_id,
                UserOrganization.organization_id == organization.id
            )
        )
    )
    user_org = user_org_result.scalar_one_or_none()
    
    if not user_org:
        raise HTTPException(
            status_code=404, 
            detail="User is not a member of this organization"
        )
    
    # Remove the relationship
    await db.delete(user_org)
    await db.commit()
    
    return {"message": "User has been removed from the organization"}


@router.put("/members/{user_id}/role")
async def update_member_role(
    user_id: UUID,
    role_data: dict,
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization),
    db: AsyncSession = Depends(get_db)
):
    """Update a member's role in the organization"""
    
    # Check if current user has admin role
    role_result = await db.execute(
        select(UserOrganization.role).where(
            and_(
                UserOrganization.user_id == current_user.id,
                UserOrganization.organization_id == organization.id
            )
        )
    )
    user_role = role_result.scalar_one_or_none()
    
    if user_role != "ADMIN":
        raise HTTPException(
            status_code=403, 
            detail="Only organization administrators can update member roles"
        )
    
    if "role" not in role_data:
        raise HTTPException(status_code=400, detail="Role is required")
    
    new_role = role_data["role"]
    if new_role not in ["ADMIN", "MEMBER"]:
        raise HTTPException(status_code=400, detail="Invalid role. Must be ADMIN or MEMBER")
    
    # Update the user's role
    await db.execute(
        update(UserOrganization).where(
            and_(
                UserOrganization.user_id == user_id,
                UserOrganization.organization_id == organization.id
            )
        ).values(role=new_role)
    )
    await db.commit()
    
    return {"message": f"User role updated to {new_role}"}


@router.get("/jurisdictions/available")
async def get_available_jurisdictions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all available jurisdictions that can be added to organization"""
    
    jurisdictions_result = await db.execute(select(Jurisdiction))
    jurisdictions = []
    
    for jurisdiction in jurisdictions_result.scalars():
        jurisdictions.append({
            "id": str(jurisdiction.id),
            "name": jurisdiction.name,
            "code": jurisdiction.code,
            "description": jurisdiction.description,
            "regulation_type": jurisdiction.regulation_type,
            "effective_date": jurisdiction.effective_date.isoformat() if jurisdiction.effective_date else None,
            "compliance_requirements": jurisdiction.compliance_requirements
        })
    
    return {"jurisdictions": jurisdictions}


@router.post("/jurisdictions/{jurisdiction_id}")
async def add_organization_jurisdiction(
    jurisdiction_id: UUID,
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization),
    db: AsyncSession = Depends(get_db)
):
    """Add a jurisdiction to the organization"""
    
    # Check if user has admin role
    role_result = await db.execute(
        select(UserOrganization.role).where(
            and_(
                UserOrganization.user_id == current_user.id,
                UserOrganization.organization_id == organization.id
            )
        )
    )
    user_role = role_result.scalar_one_or_none()
    
    if user_role != "ADMIN":
        raise HTTPException(
            status_code=403, 
            detail="Only organization administrators can manage jurisdictions"
        )
    
    # Check if jurisdiction exists
    jurisdiction_result = await db.execute(
        select(Jurisdiction).where(Jurisdiction.id == jurisdiction_id)
    )
    jurisdiction = jurisdiction_result.scalar_one_or_none()
    
    if not jurisdiction:
        raise HTTPException(status_code=404, detail="Jurisdiction not found")
    
    # Check if already added
    existing_result = await db.execute(
        select(OrganizationJurisdiction).where(
            and_(
                OrganizationJurisdiction.organization_id == organization.id,
                OrganizationJurisdiction.jurisdiction_id == jurisdiction_id
            )
        )
    )
    
    if existing_result.scalar_one_or_none():
        raise HTTPException(
            status_code=400, 
            detail="Jurisdiction is already added to this organization"
        )
    
    # Add jurisdiction to organization
    org_jurisdiction = OrganizationJurisdiction(
        organization_id=organization.id,
        jurisdiction_id=jurisdiction_id
    )
    
    db.add(org_jurisdiction)
    await db.commit()
    
    return {
        "message": f"Jurisdiction {jurisdiction.name} has been added to the organization"
    }


@router.delete("/jurisdictions/{jurisdiction_id}")
async def remove_organization_jurisdiction(
    jurisdiction_id: UUID,
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization),
    db: AsyncSession = Depends(get_db)
):
    """Remove a jurisdiction from the organization"""
    
    # Check if user has admin role
    role_result = await db.execute(
        select(UserOrganization.role).where(
            and_(
                UserOrganization.user_id == current_user.id,
                UserOrganization.organization_id == organization.id
            )
        )
    )
    user_role = role_result.scalar_one_or_none()
    
    if user_role != "ADMIN":
        raise HTTPException(
            status_code=403, 
            detail="Only organization administrators can manage jurisdictions"
        )
    
    # Find the organization jurisdiction relationship
    org_jurisdiction_result = await db.execute(
        select(OrganizationJurisdiction).where(
            and_(
                OrganizationJurisdiction.organization_id == organization.id,
                OrganizationJurisdiction.jurisdiction_id == jurisdiction_id
            )
        )
    )
    org_jurisdiction = org_jurisdiction_result.scalar_one_or_none()
    
    if not org_jurisdiction:
        raise HTTPException(
            status_code=404, 
            detail="Jurisdiction is not associated with this organization"
        )
    
    # Remove the relationship
    await db.delete(org_jurisdiction)
    await db.commit()
    
    return {"message": "Jurisdiction has been removed from the organization"}