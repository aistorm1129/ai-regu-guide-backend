from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.database import get_db
from app.api.deps import get_current_user, get_current_verified_user, get_user_organization
from app.models.user import User
from app.models.document import Document, DocumentAnalysis, DocumentType, AnalysisStatus
from app.models.organization import Organization
from app.models.jurisdiction import Jurisdiction
from app.services.document_processor import document_processor
from app.services.openai_service import openai_service
from app.services.seed_data import database_seeder
from app.config import settings
from typing import List, Optional
from uuid import UUID
import os
import aiofiles
from datetime import datetime
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

# Ensure upload directory exists
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)


@router.post("/upload")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    document_type: str = Form("OTHER"),
    description: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization),
    db: AsyncSession = Depends(get_db)
):
    """Upload a document for compliance analysis"""
    
    # Validate file
    if not document_processor.is_supported_format(file.filename):
        raise HTTPException(
            status_code=400, 
            detail="Unsupported file format. Supported formats: PDF, DOCX, DOC, TXT"
        )
    
    # Read file content
    content = await file.read()
    
    if not document_processor.validate_file_size(len(content), settings.MAX_FILE_SIZE):
        raise HTTPException(
            status_code=400, 
            detail=f"File too large. Maximum size: {settings.MAX_FILE_SIZE // 1024 // 1024}MB"
        )
    
    # Generate unique filename
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{file.filename}"
    file_path = os.path.join(settings.UPLOAD_DIR, filename)
    
    # Save file
    async with aiofiles.open(file_path, "wb") as f:
        await f.write(content)
    
    # Create document record
    document = Document(
        organization_id=organization.id,
        filename=file.filename,
        file_path=file_path,
        file_size=len(content),
        mime_type=file.content_type,
        document_type=DocumentType(document_type),
        description=description,
        uploaded_by=current_user.id,
        upload_date=datetime.utcnow()
    )
    
    db.add(document)
    await db.flush()
    await db.refresh(document)
    
    # Start background analysis
    background_tasks.add_task(
        analyze_document_background, 
        document.id, 
        file_path, 
        file.filename,
        organization.id,
        db
    )
    
    return {
        "id": str(document.id),
        "filename": document.filename,
        "file_size": len(content),
        "document_type": document_type,
        "status": "uploaded",
        "message": "Document uploaded successfully. Analysis started."
    }


async def analyze_document_background(
    document_id: UUID, 
    file_path: str, 
    filename: str,
    organization_id: UUID,
    db: AsyncSession
):
    """Background task to analyze document"""
    try:
        # Extract text from document
        extracted_text, file_type = document_processor.extract_text_from_file(file_path, filename)
        
        if file_type == 'error':
            logger.error(f"Failed to extract text from {filename}")
            return
        
        # Get organization's jurisdictions
        result = await db.execute(
            select(Jurisdiction).join(Jurisdiction.organization_jurisdictions).where(
                Jurisdiction.organization_jurisdictions.any(organization_id=organization_id)
            )
        )
        jurisdictions = result.scalars().all()
        
        if not jurisdictions:
            logger.warning(f"No jurisdictions found for organization {organization_id}")
            return
        
        # Combine all compliance requirements
        all_rules = []
        for jurisdiction in jurisdictions:
            if jurisdiction.compliance_requirements:
                all_rules.extend(jurisdiction.compliance_requirements)
        
        # Create analysis record
        analysis = DocumentAnalysis(
            document_id=document_id,
            analysis_type="compliance_check",
            status=AnalysisStatus.IN_PROGRESS,
            extracted_text=extracted_text[:5000]  # Store first 5000 chars
        )
        
        db.add(analysis)
        await db.flush()
        
        # Perform AI analysis
        analysis_result = await openai_service.analyze_document_compliance(
            extracted_text, 
            all_rules,
            "policy"  # Default document type
        )
        
        # Update analysis with results
        analysis.status = AnalysisStatus.COMPLETED
        analysis.result = analysis_result
        analysis.completed_at = datetime.utcnow()
        
        await db.commit()
        logger.info(f"Document analysis completed for {filename}")
        
    except Exception as e:
        logger.error(f"Document analysis failed for {filename}: {e}")
        # Mark analysis as failed
        try:
            analysis.status = AnalysisStatus.FAILED
            analysis.error_message = str(e)
            await db.commit()
        except:
            pass


@router.get("/")
async def list_documents(
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization),
    db: AsyncSession = Depends(get_db)
):
    """List all documents for current user's organization"""
    
    result = await db.execute(
        select(Document, DocumentAnalysis).outerjoin(DocumentAnalysis).where(
            Document.organization_id == organization.id
        ).order_by(Document.upload_date.desc())
    )
    
    documents_data = []
    for document, analysis in result:
        doc_data = {
            "id": str(document.id),
            "filename": document.filename,
            "document_type": document.document_type.value,
            "file_size": document.file_size,
            "upload_date": document.upload_date.isoformat(),
            "description": document.description,
            "uploaded_by": str(document.uploaded_by),
            "status": "processed" if analysis and analysis.status == AnalysisStatus.COMPLETED else "processing"
        }
        
        if analysis:
            doc_data.update({
                "analysis_status": analysis.status.value,
                "analysis_result": analysis.result if analysis.status == AnalysisStatus.COMPLETED else None,
                "analysis_completed": analysis.completed_at.isoformat() if analysis.completed_at else None
            })
        
        documents_data.append(doc_data)
    
    return documents_data


@router.get("/{document_id}")
async def get_document(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization),
    db: AsyncSession = Depends(get_db)
):
    """Get document details and analysis results"""
    
    result = await db.execute(
        select(Document, DocumentAnalysis).outerjoin(DocumentAnalysis).where(
            and_(
                Document.id == document_id,
                Document.organization_id == organization.id
            )
        )
    )
    
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Document not found")
    
    document, analysis = row
    
    doc_data = {
        "id": str(document.id),
        "filename": document.filename,
        "document_type": document.document_type.value,
        "file_size": document.file_size,
        "mime_type": document.mime_type,
        "upload_date": document.upload_date.isoformat(),
        "description": document.description,
        "uploaded_by": str(document.uploaded_by)
    }
    
    if analysis:
        doc_data.update({
            "analysis": {
                "status": analysis.status.value,
                "result": analysis.result,
                "completed_at": analysis.completed_at.isoformat() if analysis.completed_at else None,
                "error_message": analysis.error_message
            }
        })
    
    return doc_data


@router.delete("/{document_id}")
async def delete_document(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization),
    db: AsyncSession = Depends(get_db)
):
    """Delete a document"""
    
    result = await db.execute(
        select(Document).where(
            and_(
                Document.id == document_id,
                Document.organization_id == organization.id
            )
        )
    )
    document = result.scalar_one_or_none()
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Delete file from storage
    try:
        if os.path.exists(document.file_path):
            os.remove(document.file_path)
    except Exception as e:
        logger.warning(f"Failed to delete file {document.file_path}: {e}")
    
    # Delete database record (cascade will delete analysis)
    await db.delete(document)
    await db.commit()
    
    return {"message": "Document deleted successfully"}


@router.post("/analyze-form")
async def analyze_form_responses(
    form_responses: dict,
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization),
    db: AsyncSession = Depends(get_db)
):
    """Analyze intelligent form responses for compliance"""
    
    # Get organization's jurisdictions
    result = await db.execute(
        select(Jurisdiction).join(Jurisdiction.organization_jurisdictions).where(
            Jurisdiction.organization_jurisdictions.any(organization_id=organization.id)
        )
    )
    jurisdictions = result.scalars().all()
    
    if not jurisdictions:
        # Seed sample data if no jurisdictions
        await database_seeder.seed_jurisdictions(db)
        await database_seeder.seed_sample_organization(db, current_user.id)
        await db.commit()
        
        # Re-fetch jurisdictions
        result = await db.execute(select(Jurisdiction))
        jurisdictions = result.scalars().all()
    
    # Combine all compliance requirements
    all_rules = []
    for jurisdiction in jurisdictions:
        if jurisdiction.compliance_requirements:
            all_rules.extend(jurisdiction.compliance_requirements)
    
    # Perform AI analysis on form responses
    analysis_result = await openai_service.analyze_form_responses(
        form_responses,
        all_rules
    )
    
    # Create a virtual document record for form analysis
    document = Document(
        organization_id=organization.id,
        filename="Intelligent_Form_Response.json",
        file_path="virtual",
        file_size=len(str(form_responses)),
        mime_type="application/json",
        document_type=DocumentType.FORM_RESPONSE,
        description="Analysis of intelligent form responses",
        uploaded_by=current_user.id,
        upload_date=datetime.utcnow()
    )
    
    db.add(document)
    await db.flush()
    
    # Create analysis record
    analysis = DocumentAnalysis(
        document_id=document.id,
        analysis_type="form_analysis",
        status=AnalysisStatus.COMPLETED,
        result=analysis_result,
        completed_at=datetime.utcnow()
    )
    
    db.add(analysis)
    await db.commit()
    
    return {
        "analysis_id": str(analysis.id),
        "document_id": str(document.id),
        "result": analysis_result,
        "message": "Form analysis completed successfully"
    }