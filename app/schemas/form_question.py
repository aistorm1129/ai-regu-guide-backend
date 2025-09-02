from pydantic import BaseModel
from typing import Optional, List, Literal, Any
from datetime import datetime
from uuid import UUID


class FormQuestionBase(BaseModel):
    category: str
    question: str
    question_type: Literal["radio", "textarea", "select", "input"]
    options: Optional[List[str]] = None
    required: bool = True
    help_text: Optional[str] = None
    order: int = 0
    jurisdictions: Optional[List[str]] = None
    is_active: bool = True


class FormQuestionCreate(FormQuestionBase):
    pass


class FormQuestionUpdate(BaseModel):
    category: Optional[str] = None
    question: Optional[str] = None
    question_type: Optional[Literal["radio", "textarea", "select", "input"]] = None
    options: Optional[List[str]] = None
    required: Optional[bool] = None
    help_text: Optional[str] = None
    order: Optional[int] = None
    jurisdictions: Optional[List[str]] = None
    is_active: Optional[bool] = None


class FormQuestionResponse(FormQuestionBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class FormResponseBase(BaseModel):
    question_id: UUID
    answer: Optional[str] = None


class FormResponseCreate(FormResponseBase):
    pass


class FormResponseUpdate(BaseModel):
    answer: Optional[str] = None


class FormResponseDetail(FormResponseBase):
    id: UUID
    organization_id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime
    question: Optional[FormQuestionResponse] = None
    
    class Config:
        from_attributes = True


class FormSubmission(BaseModel):
    responses: List[FormResponseBase]


class FormQuestionsForJurisdiction(BaseModel):
    jurisdiction_ids: List[str]