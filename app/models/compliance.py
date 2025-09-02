from sqlalchemy import Column, String, DateTime, ForeignKey, Enum, Text, Float, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum
from app.database import Base


class TaskStatus(str, enum.Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class TaskPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ReportType(str, enum.Enum):
    COMPLIANCE_SUMMARY = "compliance_summary"
    GAP_ANALYSIS = "gap_analysis"
    RISK_ASSESSMENT = "risk_assessment"
    AUDIT_REPORT = "audit_report"
    EXECUTIVE_SUMMARY = "executive_summary"
    DETAILED_COMPLIANCE = "detailed_compliance"


class AIRiskLevel(str, enum.Enum):
    MINIMAL = "minimal"
    LIMITED = "limited"
    HIGH = "high"
    UNACCEPTABLE = "unacceptable"


class ComplianceTask(Base):
    __tablename__ = "compliance_tasks"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    jurisdiction_id = Column(UUID(as_uuid=True), ForeignKey("jurisdictions.id", ondelete="SET NULL"), nullable=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(Enum(TaskStatus), default=TaskStatus.TODO, nullable=False)
    priority = Column(Enum(TaskPriority), default=TaskPriority.MEDIUM, nullable=False)
    assignee_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    due_date = Column(DateTime, nullable=True)
    completed_date = Column(DateTime, nullable=True)
    estimated_hours = Column(Float, nullable=True)
    actual_hours = Column(Float, nullable=True) 
    completion_percentage = Column(Float, default=0.0, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    task_metadata = Column(JSONB, nullable=True)  # Additional task data
    
    # Relationships
    organization = relationship("Organization", back_populates="compliance_tasks")
    jurisdiction = relationship("Jurisdiction", back_populates="compliance_tasks")
    assignee = relationship("User", back_populates="assigned_tasks")


class ComplianceReport(Base):
    __tablename__ = "compliance_reports"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    report_type = Column(Enum(ReportType), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    file_path = Column(String(500), nullable=True)  # Generated report file
    data = Column(JSONB, nullable=True)  # Report data
    generated_date = Column(DateTime, default=datetime.utcnow)
    valid_until = Column(DateTime, nullable=True)
    
    # Relationships
    organization = relationship("Organization", back_populates="compliance_reports")


class AISystem(Base):
    __tablename__ = "ai_systems"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    system_type = Column(String(100), nullable=True)  # e.g., "recommendation", "risk_assessment", "decision_making"
    risk_level = Column(Enum(AIRiskLevel), nullable=True)
    is_high_risk = Column(Boolean, default=False)
    deployment_date = Column(DateTime, nullable=True)
    last_assessment = Column(DateTime, nullable=True)
    system_metadata = Column(JSONB, nullable=True)  # System specifications, features, etc.
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    organization = relationship("Organization", back_populates="ai_systems")
    compliance_records = relationship("SystemCompliance", back_populates="ai_system", cascade="all, delete-orphan")


class SystemCompliance(Base):
    __tablename__ = "system_compliance"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    system_id = Column(UUID(as_uuid=True), ForeignKey("ai_systems.id", ondelete="CASCADE"), nullable=False)
    jurisdiction_id = Column(UUID(as_uuid=True), ForeignKey("jurisdictions.id", ondelete="CASCADE"), nullable=False)
    compliance_score = Column(Float, nullable=True)  # 0.0 to 100.0
    last_assessment = Column(DateTime, nullable=True)
    assessment_results = Column(JSONB, nullable=True)
    gaps_identified = Column(JSONB, nullable=True)
    remediation_plan = Column(JSONB, nullable=True)
    
    # Relationships
    ai_system = relationship("AISystem", back_populates="compliance_records")
    jurisdiction = relationship("Jurisdiction", back_populates="system_compliance")