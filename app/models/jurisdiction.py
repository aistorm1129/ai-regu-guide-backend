from sqlalchemy import Column, String, DateTime, ForeignKey, Enum, Float, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum
from app.database import Base


class RegulationType(str, enum.Enum):
    EU_AI_ACT = "eu_ai_act"
    US_AI_GOVERNANCE = "us_ai_governance"
    ISO_42001 = "iso_42001"
    GDPR = "gdpr"
    CCPA = "ccpa"
    CUSTOM = "custom"


class ComplianceStatus(str, enum.Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    PARTIALLY_COMPLIANT = "partially_compliant"
    COMPLIANT = "compliant"
    NON_COMPLIANT = "non_compliant"


class Jurisdiction(Base):
    __tablename__ = "jurisdictions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, unique=True)
    regulation_type = Column(Enum(RegulationType), nullable=False)
    description = Column(Text, nullable=True)
    requirements = Column(JSONB, nullable=True)  # Structured requirements data
    region = Column(String(100), nullable=True)  # e.g., "EU", "US", "Global"
    effective_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    organizations = relationship("OrganizationJurisdiction", back_populates="jurisdiction")
    compliance_tasks = relationship("ComplianceTask", back_populates="jurisdiction")
    system_compliance = relationship("SystemCompliance", back_populates="jurisdiction")


class OrganizationJurisdiction(Base):
    __tablename__ = "organization_jurisdictions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    jurisdiction_id = Column(UUID(as_uuid=True), ForeignKey("jurisdictions.id", ondelete="CASCADE"), nullable=False)
    compliance_status = Column(Enum(ComplianceStatus), default=ComplianceStatus.NOT_STARTED, nullable=False)
    compliance_score = Column(Float, nullable=True)  # 0.0 to 100.0
    setup_date = Column(DateTime, default=datetime.utcnow)
    last_assessment_date = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)
    
    # Relationships
    organization = relationship("Organization", back_populates="jurisdictions")
    jurisdiction = relationship("Jurisdiction", back_populates="organizations")