from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID
from app.models.compliance import TaskStatus, TaskPriority, ReportType
from app.models.jurisdiction import ComplianceStatus


class ComplianceTaskBase(BaseModel):
    title: str
    description: Optional[str] = None
    priority: TaskPriority = TaskPriority.MEDIUM
    due_date: Optional[datetime] = None
    jurisdiction_id: Optional[UUID] = None


class ComplianceTaskCreate(ComplianceTaskBase):
    assignee_id: Optional[UUID] = None


class ComplianceTaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[TaskStatus] = None
    priority: Optional[TaskPriority] = None
    assignee_id: Optional[UUID] = None
    due_date: Optional[datetime] = None


class ComplianceTaskResponse(ComplianceTaskBase):
    id: UUID
    organization_id: UUID
    status: TaskStatus
    assignee_id: Optional[UUID]
    created_at: datetime
    updated_at: datetime
    completed_date: Optional[datetime]
    
    class Config:
        from_attributes = True


class ComplianceReportResponse(BaseModel):
    id: UUID
    organization_id: UUID
    report_type: ReportType
    title: str
    description: Optional[str]
    generated_date: datetime
    valid_until: Optional[datetime]
    
    class Config:
        from_attributes = True


class DashboardStats(BaseModel):
    overall_compliance: float = Field(..., ge=0, le=100)
    active_rules: int
    team_members: int
    reports_generated: int
    compliance_by_framework: Dict[str, float]
    recent_tasks: List[ComplianceTaskResponse]
    compliance_trends: List[Dict[str, Any]]


class JurisdictionResponse(BaseModel):
    id: UUID
    name: str
    regulation_type: str
    description: Optional[str]
    region: Optional[str]
    effective_date: Optional[datetime]
    
    class Config:
        from_attributes = True


class OrganizationJurisdictionResponse(BaseModel):
    id: UUID
    jurisdiction: JurisdictionResponse
    compliance_status: ComplianceStatus
    compliance_score: Optional[float]
    setup_date: datetime
    last_assessment_date: Optional[datetime]
    
    class Config:
        from_attributes = True