from sqlalchemy import Column, String, Boolean, DateTime, Enum, UUID as SQLAlchemyUUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum
from app.database import Base


class PlanType(str, enum.Enum):
    BASIC = "basic"
    PROFESSIONAL = "professional"


class User(Base):
    __tablename__ = "users"
    
    id = Column(SQLAlchemyUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=True)  # Nullable for OAuth-only users
    full_name = Column(String(255), nullable=True)
    plan = Column(Enum(PlanType), default=PlanType.BASIC, nullable=False)
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    is_superuser = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    organizations = relationship("UserOrganization", back_populates="user", cascade="all, delete-orphan")
    uploaded_documents = relationship("Document", back_populates="uploader")
    assigned_tasks = relationship("ComplianceTask", back_populates="assignee")