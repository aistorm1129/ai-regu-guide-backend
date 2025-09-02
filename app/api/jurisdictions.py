from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.schemas.compliance import JurisdictionResponse, OrganizationJurisdictionResponse
from app.api.deps import get_current_verified_user
from app.models.user import User
from app.models.jurisdiction import Jurisdiction, OrganizationJurisdiction
from typing import List
from uuid import UUID

router = APIRouter()


@router.get("/", response_model=List[JurisdictionResponse])
async def get_jurisdictions(
    db: AsyncSession = Depends(get_db)
):
    """Get all available jurisdictions"""
    result = await db.execute(select(Jurisdiction))
    jurisdictions = result.scalars().all()
    return jurisdictions


@router.get("/{jurisdiction_id}", response_model=JurisdictionResponse)
async def get_jurisdiction(
    jurisdiction_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get specific jurisdiction details"""
    result = await db.execute(
        select(Jurisdiction).where(Jurisdiction.id == jurisdiction_id)
    )
    jurisdiction = result.scalar_one_or_none()
    
    if not jurisdiction:
        raise HTTPException(status_code=404, detail="Jurisdiction not found")
    
    return jurisdiction


@router.post("/organizations/{org_id}/setup")
async def setup_jurisdiction(
    org_id: UUID,
    jurisdiction_id: UUID,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db)
):
    """Setup jurisdiction for an organization"""
    # TODO: Check user has permission for this organization
    
    # Check if jurisdiction exists
    result = await db.execute(
        select(Jurisdiction).where(Jurisdiction.id == jurisdiction_id)
    )
    jurisdiction = result.scalar_one_or_none()
    
    if not jurisdiction:
        raise HTTPException(status_code=404, detail="Jurisdiction not found")
    
    # Create organization-jurisdiction link
    org_jurisdiction = OrganizationJurisdiction(
        organization_id=org_id,
        jurisdiction_id=jurisdiction_id
    )
    
    db.add(org_jurisdiction)
    await db.commit()
    
    return {"message": "Jurisdiction setup completed"}