from sqlalchemy import Column, String, DateTime, ForeignKey, Enum, Text, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum
from app.database import Base


class DocumentType(str, enum.Enum):
    POLICY = "policy"
    PROCEDURE = "procedure"
    RISK_ASSESSMENT = "risk_assessment"
    AUDIT_REPORT = "audit_report"
    COMPLIANCE_CERTIFICATE = "compliance_certificate"
    TECHNICAL_DOCUMENTATION = "technical_documentation"
    DATA_PROTECTION = "data_protection"
    OTHER = "other"


class AnalysisStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class Document(Base):
    __tablename__ = "documents"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)  # S3 URL or local path
    file_size = Column(Integer, nullable=True)  # in bytes
    mime_type = Column(String(100), nullable=True)
    document_type = Column(Enum(DocumentType), nullable=False, default=DocumentType.OTHER)
    description = Column(Text, nullable=True)
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    upload_date = Column(DateTime, default=datetime.utcnow)
    file_metadata = Column(JSONB, nullable=True)  # Additional metadata
    
    # Relationships
    organization = relationship("Organization", back_populates="documents")
    uploader = relationship("User", back_populates="uploaded_documents")
    analyses = relationship("DocumentAnalysis", back_populates="document", cascade="all, delete-orphan")


class DocumentAnalysis(Base):
    __tablename__ = "document_analyses"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    analysis_type = Column(String(100), nullable=False)  # e.g., "compliance_check", "risk_assessment"
    status = Column(Enum(AnalysisStatus), default=AnalysisStatus.PENDING, nullable=False)
    result = Column(JSONB, nullable=True)  # Structured analysis results
    compliance_gaps = Column(JSONB, nullable=True)  # Identified gaps
    recommendations = Column(JSONB, nullable=True)  # Suggested actions
    confidence_score = Column(Integer, nullable=True)  # 0-100
    error_message = Column(Text, nullable=True)  # If analysis failed
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    
    # Relationships
    document = relationship("Document", back_populates="analyses")