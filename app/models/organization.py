from sqlalchemy import Column, String, DateTime, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum
from app.database import Base


class OrganizationSize(str, enum.Enum):
    SMALL = "small"  # < 50 employees
    MEDIUM = "medium"  # 50-250 employees
    LARGE = "large"  # 250+ employees
    ENTERPRISE = "enterprise"  # 1000+ employees


class UserRole(str, enum.Enum):
    OWNER = "owner"
    ADMIN = "admin"
    COMPLIANCE_OFFICER = "compliance_officer"
    MEMBER = "member"
    VIEWER = "viewer"


class Organization(Base):
    __tablename__ = "organizations"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    industry = Column(String(100), nullable=True)
    size = Column(Enum(OrganizationSize), nullable=True)
    country = Column(String(100), nullable=True)
    description = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    users = relationship("UserOrganization", back_populates="organization", cascade="all, delete-orphan")
    jurisdictions = relationship("OrganizationJurisdiction", back_populates="organization", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="organization", cascade="all, delete-orphan")
    compliance_tasks = relationship("ComplianceTask", back_populates="organization", cascade="all, delete-orphan")
    compliance_reports = relationship("ComplianceReport", back_populates="organization", cascade="all, delete-orphan")
    ai_systems = relationship("AISystem", back_populates="organization", cascade="all, delete-orphan")


class UserOrganization(Base):
    __tablename__ = "user_organizations"
    
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True)
    role = Column(Enum(UserRole), nullable=False, default=UserRole.MEMBER)
    joined_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="organizations")
    organization = relationship("Organization", back_populates="users")