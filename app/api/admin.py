from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.database import get_db
from app.api.deps import get_current_user, require_admin_role
from app.models.user import User
from app.models.jurisdiction import Jurisdiction
from app.models.compliance import ComplianceDocument, ComplianceRequirement
from app.services.document_processor import document_processor
from app.services.compliance_extractor import ComplianceExtractor
from app.config import settings
from typing import List, Optional
from uuid import UUID
import os
import aiofiles
from datetime import datetime
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

# Ensure compliance documents directory exists
COMPLIANCE_DOCS_DIR = os.path.join(settings.UPLOAD_DIR, "compliance-docs")
os.makedirs(COMPLIANCE_DOCS_DIR, exist_ok=True)


@router.post("/compliance-documents/upload")
async def upload_compliance_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    jurisdiction_id: str = Form(...),
    title: str = Form(...),
    document_type: str = Form("official_text"),  # official_text, guidance, implementation
    version: Optional[str] = Form(None),
    effective_date: Optional[str] = Form(None),
    current_user: User = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db)
):
    """Upload compliance document (Admin only)"""
    
    # Validate file format
    if not document_processor.is_supported_format(file.filename):
        raise HTTPException(
            status_code=400, 
            detail="Unsupported file format. Only PDF files supported for compliance documents."
        )
    
    # Validate jurisdiction exists
    result = await db.execute(select(Jurisdiction).where(Jurisdiction.id == jurisdiction_id))
    jurisdiction = result.scalar_one_or_none()
    if not jurisdiction:
        raise HTTPException(status_code=404, detail="Jurisdiction not found")
    
    # Read and validate file
    content = await file.read()
    if len(content) > settings.MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large")
    
    # Create framework-specific directory
    framework_dir = os.path.join(COMPLIANCE_DOCS_DIR, jurisdiction.regulation_type.value)
    os.makedirs(framework_dir, exist_ok=True)
    
    # Generate unique filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{file.filename}"
    file_path = os.path.join(framework_dir, filename)
    
    # Save file
    async with aiofiles.open(file_path, 'wb') as f:
        await f.write(content)
    
    # Create database record
    compliance_doc = ComplianceDocument(
        jurisdiction_id=jurisdiction_id,
        title=title,
        document_type=document_type,
        file_path=file_path,
        version=version,
        effective_date=datetime.fromisoformat(effective_date) if effective_date else None,
        uploaded_by=current_user.id,
        processing_status='pending'
    )
    
    db.add(compliance_doc)
    await db.flush()
    
    # Queue background processing
    background_tasks.add_task(
        process_compliance_document,
        str(compliance_doc.id),
        file_path,
        jurisdiction.regulation_type.value
    )

    await db.commit()

    return {
        "id": str(compliance_doc.id),
        "title": title,
        "status": "uploaded",
        "message": "Compliance document uploaded successfully. Processing will begin shortly.",
        "processing_note": "Check browser console and backend logs to see extraction method (Assistant API vs Chunking)"
    }


@router.get("/compliance-documents")
async def list_compliance_documents(
    jurisdiction_id: Optional[str] = None,
    current_user: User = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db)
):
    """List all compliance documents (Admin only)"""

    # Query documents without relationships to avoid async issues
    query = select(ComplianceDocument)

    if jurisdiction_id:
        query = query.where(ComplianceDocument.jurisdiction_id == jurisdiction_id)

    result = await db.execute(query)
    documents = result.scalars().all()

    # Get all jurisdiction IDs for a separate query
    jurisdiction_ids = {doc.jurisdiction_id for doc in documents if doc.jurisdiction_id}

    # Get jurisdictions in a separate query
    jurisdictions_map = {}
    if jurisdiction_ids:
        from app.models.jurisdiction import Jurisdiction
        jurisdiction_result = await db.execute(
            select(Jurisdiction).where(Jurisdiction.id.in_(jurisdiction_ids))
        )
        jurisdictions = jurisdiction_result.scalars().all()
        jurisdictions_map = {str(j.id): j for j in jurisdictions}

    # Get requirements count for each document
    requirements_count_map = {}
    if documents:
        doc_ids = [str(doc.id) for doc in documents]
        from sqlalchemy import func
        count_result = await db.execute(
            select(
                ComplianceRequirement.source_document_id,
                func.count(ComplianceRequirement.id).label('count')
            ).where(
                ComplianceRequirement.source_document_id.in_(doc_ids)
            ).group_by(ComplianceRequirement.source_document_id)
        )
        requirements_count_map = {str(row[0]): row[1] for row in count_result.all()}

    return {
        "documents": [
            {
                "id": str(doc.id),
                "title": doc.title,
                "document_type": doc.document_type,
                "version": doc.version,
                "effective_date": doc.effective_date.isoformat() if doc.effective_date else None,
                "upload_date": doc.upload_date.isoformat(),
                "is_processed": doc.is_processed,
                "processing_status": doc.processing_status,
                "jurisdiction": {
                    "id": str(doc.jurisdiction_id),
                    "name": jurisdictions_map[str(doc.jurisdiction_id)].name,
                    "regulation_type": jurisdictions_map[str(doc.jurisdiction_id)].regulation_type.value
                } if doc.jurisdiction_id and str(doc.jurisdiction_id) in jurisdictions_map else None,
                "requirements_count": requirements_count_map.get(str(doc.id), 0),
                "uploaded_by": str(doc.uploaded_by)
            }
            for doc in documents
        ]
    }


@router.get("/compliance-documents/{document_id}/requirements")
async def get_document_requirements(
    document_id: str,
    current_user: User = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db)
):
    """Get extracted requirements from a compliance document"""
    
    result = await db.execute(
        select(ComplianceRequirement)
        .where(ComplianceRequirement.source_document_id == document_id)
        .order_by(ComplianceRequirement.requirement_id)
    )
    requirements = result.scalars().all()
    
    return {
        "requirements": [
            {
                "id": str(req.id),
                "requirement_id": req.requirement_id,
                "title": req.title,
                "category": req.category,
                "description": req.description,
                "page_number": req.page_number,
                "section_reference": req.section_reference,
                "criticality": req.criticality,
                "is_active": req.is_active
            }
            for req in requirements
        ]
    }


@router.delete("/compliance-documents/{document_id}")
async def delete_compliance_document(
    document_id: str,
    current_user: User = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db)
):
    """Delete compliance document and its requirements"""

    result = await db.execute(
        select(ComplianceDocument).where(ComplianceDocument.id == document_id)
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(status_code=404, detail="Compliance document not found")

    # Delete file
    if os.path.exists(document.file_path):
        os.remove(document.file_path)

    # Delete database record (requirements will be cascade deleted)
    await db.delete(document)
    await db.commit()

    return {"message": "Compliance document deleted successfully"}


@router.get("/assistants")
async def list_assistants(
    current_user: User = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db)
):
    """List all configured assistants for jurisdictions (Admin only)"""

    result = await db.execute(
        select(Jurisdiction).where(Jurisdiction.assistant_id.isnot(None))
    )
    jurisdictions_with_assistants = result.scalars().all()

    return {
        "assistants": [
            {
                "jurisdiction_id": str(jurisdiction.id),
                "jurisdiction_name": jurisdiction.name,
                "regulation_type": jurisdiction.regulation_type.value,
                "assistant_id": jurisdiction.assistant_id,
                "vector_store_id": jurisdiction.vector_store_id,
                "created_at": jurisdiction.created_at.isoformat() if jurisdiction.created_at else None,
                "compliance_documents_count": len(jurisdiction.compliance_documents) if hasattr(jurisdiction, 'compliance_documents') else 0,
                "requirements_count": len(jurisdiction.requirements) if hasattr(jurisdiction, 'requirements') else 0
            }
            for jurisdiction in jurisdictions_with_assistants
        ],
        "total": len(jurisdictions_with_assistants)
    }


@router.delete("/assistants/{jurisdiction_id}")
async def remove_assistant(
    jurisdiction_id: str,
    current_user: User = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db)
):
    """Remove assistant from jurisdiction and optionally delete from OpenAI (Admin only)"""

    result = await db.execute(
        select(Jurisdiction).where(Jurisdiction.id == jurisdiction_id)
    )
    jurisdiction = result.scalar_one_or_none()

    if not jurisdiction:
        raise HTTPException(status_code=404, detail="Jurisdiction not found")

    if not jurisdiction.assistant_id:
        raise HTTPException(status_code=400, detail="Jurisdiction has no assistant configured")

    assistant_id = jurisdiction.assistant_id
    vector_store_id = jurisdiction.vector_store_id

    # Clear assistant references
    jurisdiction.assistant_id = None
    jurisdiction.vector_store_id = None
    await db.commit()

    # Optionally delete from OpenAI (uncomment if you want to delete the assistant)
    # from app.services.assistant_manager import assistant_manager
    # await assistant_manager.cleanup_assistant(assistant_id, vector_store_id)

    return {
        "message": f"Assistant {assistant_id} removed from jurisdiction {jurisdiction.name}",
        "note": "Assistant still exists in OpenAI. Uncomment cleanup code to delete it."
    }


@router.post("/assistants/{jurisdiction_id}/refresh")
async def refresh_assistant(
    jurisdiction_id: str,
    current_user: User = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db)
):
    """Recreate assistant for jurisdiction with latest compliance documents (Admin only)"""

    result = await db.execute(
        select(Jurisdiction).where(Jurisdiction.id == jurisdiction_id)
    )
    jurisdiction = result.scalar_one_or_none()

    if not jurisdiction:
        raise HTTPException(status_code=404, detail="Jurisdiction not found")

    # Get latest compliance document for this jurisdiction
    doc_result = await db.execute(
        select(ComplianceDocument)
        .where(ComplianceDocument.jurisdiction_id == jurisdiction_id)
        .order_by(ComplianceDocument.upload_date.desc())
        .limit(1)
    )
    latest_document = doc_result.scalar_one_or_none()

    if not latest_document:
        raise HTTPException(status_code=400, detail="No compliance documents found for this jurisdiction")

    # Delete old assistant if exists
    if jurisdiction.assistant_id:
        from app.services.assistant_manager import assistant_manager
        try:
            await assistant_manager.cleanup_assistant(
                jurisdiction.assistant_id,
                jurisdiction.vector_store_id
            )
        except Exception as e:
            logger.warning(f"Failed to cleanup old assistant: {e}")

    # Create new assistant
    from app.services.compliance_extractor import ComplianceExtractor
    extractor = ComplianceExtractor()

    _, extraction_metadata = await extractor.extract_requirements(
        latest_document.file_path,
        jurisdiction.regulation_type.value,
        use_assistant_api=True,
        keep_assistant=True
    )

    # Update jurisdiction with new assistant
    jurisdiction.assistant_id = extraction_metadata.get('assistant_id')
    jurisdiction.vector_store_id = extraction_metadata.get('vector_store_id')
    await db.commit()

    return {
        "message": f"Assistant refreshed for {jurisdiction.name}",
        "assistant_id": jurisdiction.assistant_id,
        "vector_store_id": jurisdiction.vector_store_id
    }


async def process_compliance_document(document_id: str, file_path: str, framework: str):
    """Background task to extract requirements from compliance document"""

    from app.database import get_async_session

    async with get_async_session() as db:
        try:
            # Update processing status
            result = await db.execute(
                select(ComplianceDocument).where(ComplianceDocument.id == document_id)
            )
            document = result.scalar_one()
            document.processing_status = 'processing'
            await db.commit()

            # Extract requirements using AI (keep_assistant=True for persistent storage)
            extractor = ComplianceExtractor()
            requirements, extraction_metadata = await extractor.extract_requirements(
                file_path, framework, use_assistant_api=True, keep_assistant=True
            )

            # Log extraction method to console (will appear in backend logs)
            logger.info(f"📋 EXTRACTION METHOD USED: {extraction_metadata.get('method', 'unknown')}")
            logger.info(f"📊 Text Length: {extraction_metadata.get('text_length', 0)} characters")

            # Save extracted text and metadata
            document.extraction_metadata = extraction_metadata
            if extraction_metadata.get('extracted_text'):
                document.extracted_text = extraction_metadata['extracted_text']
                logger.info(f"💾 Full text saved to database ({len(extraction_metadata['extracted_text'])} chars)")
            else:
                logger.info("📁 Assistant API used - full text not available for storage")

            # Save Assistant ID to jurisdiction for future document comparisons
            if extraction_metadata.get('assistant_id'):
                logger.info(f"🤖 Saving persistent Assistant ID: {extraction_metadata['assistant_id']}")

                # Get the jurisdiction and update with assistant data
                jurisdiction_result = await db.execute(
                    select(Jurisdiction).where(Jurisdiction.id == document.jurisdiction_id)
                )
                jurisdiction = jurisdiction_result.scalar_one()

                # Update or create assistant reference
                if not jurisdiction.assistant_id:
                    jurisdiction.assistant_id = extraction_metadata['assistant_id']
                    jurisdiction.vector_store_id = extraction_metadata.get('vector_store_id')
                    logger.info(f"✅ Saved Assistant to jurisdiction: {jurisdiction.name}")
                else:
                    logger.info(f"⚠️ Jurisdiction already has Assistant: {jurisdiction.assistant_id}")
                    # Optionally, you could update the existing assistant or merge vector stores

                await db.commit()

            # Save extracted requirements to database
            for req_data in requirements:
                requirement = ComplianceRequirement(
                    jurisdiction_id=document.jurisdiction_id,
                    source_document_id=document.id,
                    requirement_id=req_data["requirement_id"],
                    title=req_data["title"],
                    category=req_data["category"],
                    description=req_data["description"],
                    page_number=req_data.get("page_number"),
                    section_reference=req_data.get("section_reference"),
                    criticality=req_data["criticality"]
                )
                db.add(requirement)
            
            # Update document status
            document.processing_status = 'completed'
            document.is_processed = True
            await db.commit()
            
            logger.info(f"Successfully processed compliance document {document_id} with {len(requirements)} requirements")
            
        except Exception as e:
            logger.error(f"Failed to process compliance document {document_id}: {e}")
            
            # Update status to failed
            result = await db.execute(
                select(ComplianceDocument).where(ComplianceDocument.id == document_id)
            )
            document = result.scalar_one()
            document.processing_status = 'failed'
            await db.commit()# Force reload
# Force reload 2
