from sqlalchemy import Column, String, DateTime, ForeignKey, Enum, Text, Boolean, Integer, Float, UUID as SQLAlchemyUUID, JSON
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
    DASHBOARD = "dashboard"
    AUDIT_REPORT = "audit_report"


class ComplianceStatus(str, enum.Enum):
    COMPLIANT = "COMPLIANT"
    PARTIAL = "PARTIAL"
    NON_COMPLIANT = "NON_COMPLIANT"
    NOT_ASSESSED = "NOT_ASSESSED"


class Criticality(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ComplianceTask(Base):
    __tablename__ = "compliance_tasks"
    
    id = Column(SQLAlchemyUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(SQLAlchemyUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    jurisdiction_id = Column(SQLAlchemyUUID(as_uuid=True), ForeignKey("jurisdictions.id", ondelete="SET NULL"), nullable=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(Enum(TaskStatus), default=TaskStatus.TODO, nullable=False)
    priority = Column(Enum(TaskPriority), default=TaskPriority.MEDIUM, nullable=False)
    assignee_id = Column(SQLAlchemyUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    due_date = Column(DateTime, nullable=True)
    completed_date = Column(DateTime, nullable=True)
    
    # Fields for automatic task generation from compliance gaps
    source_type = Column(String(50), nullable=True)  # 'gap_analysis', 'manual'
    source_id = Column(SQLAlchemyUUID(as_uuid=True), nullable=True)  # Reference to gap/requirement
    requirement_id = Column(String(255), nullable=True)  # Specific requirement ID
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    organization = relationship("Organization", back_populates="compliance_tasks")
    jurisdiction = relationship("Jurisdiction", back_populates="compliance_tasks")
    assignee = relationship("User", back_populates="assigned_tasks")


class ComplianceReport(Base):
    __tablename__ = "compliance_reports"
    
    id = Column(SQLAlchemyUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(SQLAlchemyUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    report_type = Column(Enum(ReportType), nullable=False)  # Only 'dashboard' or 'audit_report'
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    file_path = Column(String(500), nullable=True)  # Generated report file
    generated_date = Column(DateTime, default=datetime.utcnow)
    valid_until = Column(DateTime, nullable=True)
    
    # Relationships
    organization = relationship("Organization", back_populates="compliance_reports")


class ComplianceDocument(Base):
    """Admin-managed compliance documents (PDFs)"""
    __tablename__ = "compliance_documents"
    
    id = Column(SQLAlchemyUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    jurisdiction_id = Column(SQLAlchemyUUID(as_uuid=True), ForeignKey("jurisdictions.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(255), nullable=False)
    document_type = Column(String(50), nullable=False)  # 'official_text', 'guidance', 'implementation'
    file_path = Column(String(500), nullable=False)
    version = Column(String(50), nullable=True)
    effective_date = Column(DateTime, nullable=True)
    uploaded_by = Column(SQLAlchemyUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    upload_date = Column(DateTime, default=datetime.utcnow)
    is_processed = Column(Boolean, default=False)
    processing_status = Column(String(20), default='pending')  # 'pending', 'processing', 'completed', 'failed'

    # Full text extraction fields (new)
    extracted_text = Column(Text, nullable=True)  # Full text extracted from PDF
    extraction_metadata = Column(JSON, nullable=True)  # Method used, text length, etc.

    # Relationships
    jurisdiction = relationship("Jurisdiction")
    uploader = relationship("User")
    requirements = relationship("ComplianceRequirement", back_populates="source_document", cascade="all, delete-orphan")


class ComplianceRequirement(Base):
    """Requirements extracted from compliance documents"""
    __tablename__ = "compliance_requirements"
    
    id = Column(SQLAlchemyUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    jurisdiction_id = Column(SQLAlchemyUUID(as_uuid=True), ForeignKey("jurisdictions.id", ondelete="CASCADE"), nullable=False)
    source_document_id = Column(SQLAlchemyUUID(as_uuid=True), ForeignKey("compliance_documents.id", ondelete="CASCADE"), nullable=True)
    requirement_id = Column(String(100), nullable=False)  # e.g., 'Article_5.1.c', 'ISO_4.1'
    title = Column(String(500), nullable=False)
    category = Column(String(255), nullable=False)  # e.g., 'Transparency', 'Risk Management'
    description = Column(Text, nullable=False)  # Full requirement description
    page_number = Column(Integer, nullable=True)  # PDF page reference
    section_reference = Column(String(100), nullable=True)  # 'Section 3.2', 'Article 5'
    criticality = Column(String(20), nullable=False)  # 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    jurisdiction = relationship("Jurisdiction", back_populates="requirements")
    source_document = relationship("ComplianceDocument", back_populates="requirements")
    assessments = relationship("ComplianceAssessment", back_populates="requirement", cascade="all, delete-orphan")


class AssessmentSession(Base):
    """Track assessment sessions for audit purposes"""
    __tablename__ = "assessment_sessions"
    
    id = Column(SQLAlchemyUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(SQLAlchemyUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    session_type = Column(String(50), nullable=False)  # 'document_upload', 'questionnaire', 'hybrid'
    source_document_name = Column(String(255), nullable=True)  # Name of uploaded document
    source_document_path = Column(String(500), nullable=True)  # Path to uploaded document
    overall_score = Column(Integer, nullable=True)  # Overall compliance percentage
    total_requirements = Column(Integer, nullable=False, default=0)
    compliant_count = Column(Integer, nullable=False, default=0)
    partial_count = Column(Integer, nullable=False, default=0)
    non_compliant_count = Column(Integer, nullable=False, default=0)
    not_addressed_count = Column(Integer, nullable=False, default=0)
    created_by = Column(SQLAlchemyUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    
    # Relationships
    organization = relationship("Organization")
    assessments = relationship("ComplianceAssessment", back_populates="session", cascade="all, delete-orphan")
    creator = relationship("User")


class ComplianceAssessment(Base):
    """Tracks compliance status for each requirement per organization"""
    __tablename__ = "compliance_assessments"
    
    id = Column(SQLAlchemyUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(SQLAlchemyUUID(as_uuid=True), ForeignKey("assessment_sessions.id", ondelete="CASCADE"), nullable=True)  # Can be null for legacy data
    organization_id = Column(SQLAlchemyUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    requirement_id = Column(SQLAlchemyUUID(as_uuid=True), ForeignKey("compliance_requirements.id", ondelete="CASCADE"), nullable=False)
    status = Column(String(20), nullable=False)  # 'COMPLIANT', 'PARTIAL', 'NON_COMPLIANT', 'NOT_ASSESSED'
    evidence_text = Column(Text, nullable=True)  # Actual evidence quote from document/response
    evidence_type = Column(String(50), nullable=True)  # 'document', 'form_response'
    evidence_id = Column(SQLAlchemyUUID(as_uuid=True), nullable=True)  # Reference to document or form response
    explanation = Column(Text, nullable=True)  # AI-generated explanation
    gap_description = Column(Text, nullable=True)  # What's missing for compliance
    recommendation = Column(Text, nullable=True)  # Specific recommendations
    confidence_score = Column(Float, nullable=True)  # AI confidence in assessment (0-1)
    assessed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    session = relationship("AssessmentSession", back_populates="assessments")
    organization = relationship("Organization", back_populates="compliance_assessments")
    requirement = relationship("ComplianceRequirement", back_populates="assessments")