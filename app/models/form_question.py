from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text, Enum, Integer
from sqlalchemy.dialects.postgresql import UUID, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum
from app.database import Base


class QuestionType(str, enum.Enum):
    RADIO = "radio"
    TEXTAREA = "textarea"
    SELECT = "select"
    INPUT = "input"


class FormQuestion(Base):
    __tablename__ = "form_questions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    category = Column(String(255), nullable=False)
    question = Column(Text, nullable=False)
    question_type = Column(Enum(QuestionType), nullable=False)
    options = Column(JSON, nullable=True)  # For select/radio questions
    required = Column(Boolean, default=True)
    help_text = Column(Text, nullable=True)
    order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, default=True)
    
    # Which jurisdictions this question applies to
    jurisdictions = Column(JSON, nullable=True)  # Array of jurisdiction IDs/codes
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class FormResponse(Base):
    __tablename__ = "form_responses"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    question_id = Column(UUID(as_uuid=True), ForeignKey("form_questions.id"), nullable=False)
    answer = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    question = relationship("FormQuestion")
    user = relationship("User", foreign_keys=[user_id])
    organization = relationship("Organization")