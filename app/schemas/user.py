from pydantic import BaseModel, EmailStr, Field, field_serializer
from typing import Optional, Literal, Any
from datetime import datetime
from uuid import UUID


class UserBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None
    plan: Optional[Literal["basic", "professional"]] = "basic"


class UserCreate(UserBase):
    password: str = Field(..., min_length=8)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    plan: Optional[Literal["basic", "professional"]] = None


class UserResponse(UserBase):
    id: UUID
    is_active: bool
    is_verified: bool
    created_at: datetime
    
    @field_serializer('plan')
    def serialize_plan(self, value: Any) -> str:
        """Convert PlanType enum to string"""
        if hasattr(value, 'value'):
            return value.value
        return value or "basic"
    
    class Config:
        from_attributes = True


class UserInDB(UserResponse):
    hashed_password: Optional[str] = None