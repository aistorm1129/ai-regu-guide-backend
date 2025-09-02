from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.schemas.compliance import DashboardStats, ComplianceTaskResponse
from app.api.deps import get_current_verified_user
from app.models.user import User
from app.models.compliance import ComplianceTask
from app.models.organization import Organization, UserOrganization
from typing import List

router = APIRouter()


@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db)
):
    """Get dashboard statistics for current user's organization"""
    
    # Get user's organization (for now, return mock data)
    # In production, fetch actual data from database
    
    recent_tasks = []
    compliance_trends = [
        {"month": "Jan", "compliance": 75},
        {"month": "Feb", "compliance": 78},
        {"month": "Mar", "compliance": 82},
        {"month": "Apr", "compliance": 85},
        {"month": "May", "compliance": 87},
        {"month": "Jun", "compliance": 89},
    ]
    
    return DashboardStats(
        overall_compliance=89.5,
        active_rules=47,
        team_members=12,
        reports_generated=8,
        compliance_by_framework={
            "EU AI Act": 92.0,
            "US AI Governance": 87.0,
            "ISO/IEC 42001": 89.0
        },
        recent_tasks=recent_tasks,
        compliance_trends=compliance_trends
    )