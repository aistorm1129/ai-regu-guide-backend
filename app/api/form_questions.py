from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from sqlalchemy.orm import joinedload
from app.database import get_db
from app.api.deps import get_current_user, get_user_organization
from app.models.user import User
from app.models.organization import Organization
from app.models.form_question import FormQuestion, FormResponse
from app.schemas.form_question import (
    FormQuestionResponse, FormQuestionCreate, FormQuestionUpdate,
    FormResponseCreate, FormResponseDetail, FormSubmission,
    FormQuestionsForJurisdiction
)
from app.services.openai_service import openai_service

router = APIRouter()


@router.get("/questions", response_model=List[FormQuestionResponse])
async def get_form_questions(
    jurisdiction_ids: List[str] = Query(default=[]),
    db: AsyncSession = Depends(get_db)
):
    """Get form questions, optionally filtered by jurisdiction"""
    query = select(FormQuestion).where(FormQuestion.is_active == True)
    
    if jurisdiction_ids:
        # Filter questions that apply to any of the specified jurisdictions
        query = query.where(
            or_(
                FormQuestion.jurisdictions.is_(None),  # Questions that apply to all
                *[FormQuestion.jurisdictions.contains([jurisdiction_id]) for jurisdiction_id in jurisdiction_ids]
            )
        )
    
    query = query.order_by(FormQuestion.order, FormQuestion.created_at)
    
    result = await db.execute(query)
    questions = result.scalars().all()
    
    return questions


@router.post("/questions", response_model=FormQuestionResponse)
async def create_form_question(
    question_data: FormQuestionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new form question (admin only)"""
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can create form questions"
        )
    
    question = FormQuestion(**question_data.model_dump())
    db.add(question)
    await db.commit()
    await db.refresh(question)
    
    return question


@router.put("/questions/{question_id}", response_model=FormQuestionResponse)
async def update_form_question(
    question_id: str,
    question_data: FormQuestionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a form question (admin only)"""
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can update form questions"
        )
    
    result = await db.execute(
        select(FormQuestion).where(FormQuestion.id == question_id)
    )
    question = result.scalar_one_or_none()
    
    if not question:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Form question not found"
        )
    
    update_data = question_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(question, field, value)
    
    await db.commit()
    await db.refresh(question)
    
    return question


@router.delete("/questions/{question_id}")
async def delete_form_question(
    question_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete (deactivate) a form question (admin only)"""
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can delete form questions"
        )
    
    result = await db.execute(
        select(FormQuestion).where(FormQuestion.id == question_id)
    )
    question = result.scalar_one_or_none()
    
    if not question:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Form question not found"
        )
    
    question.is_active = False
    await db.commit()
    
    return {"message": "Form question deleted successfully"}


@router.post("/responses", response_model=List[FormResponseDetail])
async def submit_form_responses(
    submission: FormSubmission,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_user_organization)
):
    """Submit form responses"""
    responses = []
    
    for response_data in submission.responses:
        # Check if response already exists
        existing_result = await db.execute(
            select(FormResponse).where(
                and_(
                    FormResponse.organization_id == current_org.id,
                    FormResponse.question_id == response_data.question_id
                )
            )
        )
        existing_response = existing_result.scalar_one_or_none()
        
        if existing_response:
            # Update existing response
            existing_response.answer = response_data.answer
            existing_response.user_id = current_user.id
            await db.flush()
            responses.append(existing_response)
        else:
            # Create new response
            new_response = FormResponse(
                organization_id=current_org.id,
                user_id=current_user.id,
                question_id=response_data.question_id,
                answer=response_data.answer
            )
            db.add(new_response)
            await db.flush()
            responses.append(new_response)
    
    await db.commit()
    
    # Fetch responses with question details
    result = await db.execute(
        select(FormResponse)
        .options(joinedload(FormResponse.question))
        .where(FormResponse.id.in_([r.id for r in responses]))
    )
    detailed_responses = result.scalars().all()
    
    # Trigger AI analysis of form responses
    try:
        # Get all jurisdiction rules for analysis
        from app.models.jurisdiction import Jurisdiction
        from app.models.organization import OrganizationJurisdiction
        
        # Get organization's jurisdictions
        jurisdictions_result = await db.execute(
            select(Jurisdiction)
            .join(OrganizationJurisdiction)
            .where(OrganizationJurisdiction.organization_id == current_org.id)
        )
        jurisdictions = jurisdictions_result.scalars().all()
        
        if jurisdictions:
            # Prepare form responses for analysis
            form_responses = {
                str(response.question_id): response.answer 
                for response in detailed_responses
            }
            
            # Get all rules from active jurisdictions
            all_rules = []
            for jurisdiction in jurisdictions:
                if hasattr(jurisdiction, 'rules') and jurisdiction.rules:
                    all_rules.extend(jurisdiction.rules)
            
            # Perform AI analysis
            await openai_service.analyze_form_responses(form_responses, all_rules)
    except Exception as e:
        # Log error but don't fail the form submission
        print(f"Error in AI analysis of form responses: {e}")
    
    return detailed_responses


@router.get("/responses", response_model=List[FormResponseDetail])
async def get_form_responses(
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_user_organization)
):
    """Get form responses for the current organization"""
    result = await db.execute(
        select(FormResponse)
        .options(joinedload(FormResponse.question))
        .where(FormResponse.organization_id == current_org.id)
        .order_by(FormResponse.created_at.desc())
    )
    responses = result.scalars().all()
    
    return responses


@router.get("/responses/{question_id}", response_model=FormResponseDetail)
async def get_form_response(
    question_id: str,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_user_organization)
):
    """Get a specific form response"""
    result = await db.execute(
        select(FormResponse)
        .options(joinedload(FormResponse.question))
        .where(
            and_(
                FormResponse.organization_id == current_org.id,
                FormResponse.question_id == question_id
            )
        )
    )
    response = result.scalar_one_or_none()
    
    if not response:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Form response not found"
        )
    
    return response