from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from app.database import get_db
from app.api.deps import get_current_user, get_current_verified_user, get_user_organization
from app.models.user import User
from app.models.organization import Organization
from app.models.document import Document, DocumentAnalysis, AnalysisStatus
from app.models.jurisdiction import Jurisdiction, OrganizationJurisdiction
from app.models.compliance import ComplianceTask, ComplianceRequirement, ComplianceAssessment, AssessmentSession
from app.services.seed_data import database_seeder
from app.services.document_assessor import document_assessor
from app.services.form_generator import form_generator
from fastapi import UploadFile, File, BackgroundTasks
from app.config import settings
import os
import aiofiles
from typing import Dict, Any, List
from uuid import UUID
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/analyze")
async def analyze_compliance(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization),
    db: AsyncSession = Depends(get_db)
):
    """Get compliance analysis results for a document"""
    
    # Get document and its analysis
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
    
    if not analysis:
        raise HTTPException(
            status_code=400, 
            detail="Document analysis not available. Please upload document first."
        )
    
    if analysis.status != AnalysisStatus.COMPLETED:
        return {
            "document_id": str(document_id),
            "status": analysis.status.value,
            "message": f"Analysis is {analysis.status.value}. Please try again later."
        }
    
    return {
        "document_id": str(document_id),
        "analysis_result": analysis.result,
        "completed_at": analysis.completed_at.isoformat(),
        "status": "completed"
    }


@router.get("/results")
async def get_compliance_results(
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization),
    db: AsyncSession = Depends(get_db)
):
    """Get all compliance analysis results for organization"""
    
    # Get all completed analyses for the organization
    result = await db.execute(
        select(Document, DocumentAnalysis).join(DocumentAnalysis).where(
            and_(
                Document.organization_id == organization.id,
                DocumentAnalysis.status == AnalysisStatus.COMPLETED
            )
        ).order_by(DocumentAnalysis.completed_at.desc())
    )
    
    analyses = []
    overall_stats = {
        "total_rules": 0,
        "conforming": 0,
        "partial": 0,
        "non_conforming": 0,
        "overall_score": 0
    }
    
    for document, analysis in result:
        if analysis.result:
            analysis_data = {
                "document_id": str(document.id),
                "document_name": document.filename,
                "analysis_id": str(analysis.id),
                "completed_at": analysis.completed_at.isoformat(),
                "result": analysis.result
            }
            analyses.append(analysis_data)
            
            # Aggregate stats
            if "summary" in analysis.result:
                summary = analysis.result["summary"]
                overall_stats["conforming"] += summary.get("conforming", 0)
                overall_stats["partial"] += summary.get("partial", 0)
                overall_stats["non_conforming"] += summary.get("non_conforming", 0)
                overall_stats["total_rules"] += (
                    summary.get("conforming", 0) + 
                    summary.get("partial", 0) + 
                    summary.get("non_conforming", 0)
                )
    
    # Calculate overall score
    if overall_stats["total_rules"] > 0:
        score = (
            (overall_stats["conforming"] * 100 + overall_stats["partial"] * 50) / 
            overall_stats["total_rules"]
        )
        overall_stats["overall_score"] = round(score, 1)
    
    return {
        "analyses": analyses,
        "summary": overall_stats,
        "total_analyses": len(analyses)
    }


@router.get("/gaps")
async def get_compliance_gaps(
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization),
    db: AsyncSession = Depends(get_db)
):
    """Get compliance gaps and recommendations"""
    
    # Get all completed analyses
    result = await db.execute(
        select(DocumentAnalysis).join(Document).where(
            and_(
                Document.organization_id == organization.id,
                DocumentAnalysis.status == AnalysisStatus.COMPLETED
            )
        )
    )
    
    analyses = result.scalars().all()
    gaps = []
    recommendations = []
    
    for analysis in analyses:
        if analysis.result and "compliance_rules" in analysis.result:
            rules = analysis.result["compliance_rules"]
            
            for rule in rules:
                if rule.get("status") in ["partial", "non_conform"]:
                    gap = {
                        "rule_id": rule.get("rule_id"),
                        "rule_title": rule.get("rule_title"),
                        "status": rule.get("status"),
                        "severity": rule.get("severity", "medium"),
                        "explanation": rule.get("explanation"),
                        "recommendation": rule.get("recommendation"),
                        "confidence": rule.get("confidence", 0)
                    }
                    gaps.append(gap)
                    
                    if rule.get("recommendation"):
                        recommendations.append({
                            "rule_id": rule.get("rule_id"),
                            "recommendation": rule.get("recommendation"),
                            "priority": "high" if rule.get("status") == "non_conform" else "medium"
                        })
    
    # Sort by severity and confidence
    gaps.sort(key=lambda x: (
        0 if x["severity"] == "high" else 1 if x["severity"] == "medium" else 2,
        -x["confidence"]
    ))
    
    return {
        "gaps": gaps,
        "recommendations": recommendations,
        "total_gaps": len(gaps),
        "critical_gaps": len([g for g in gaps if g["severity"] == "high"])
    }


@router.get("/rules")
async def get_compliance_rules(
    regulation_filter: str = None,
    status_filter: str = None,
    severity_filter: str = None,
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization),
    db: AsyncSession = Depends(get_db)
):
    """Get detailed compliance rules with their current status from extracted requirements"""
    
    # Get organization's selected jurisdictions
    org_jurisdictions_result = await db.execute(
        select(Jurisdiction)
        .join(OrganizationJurisdiction)
        .where(OrganizationJurisdiction.organization_id == organization.id)
    )
    org_jurisdictions = org_jurisdictions_result.scalars().all()
    
    if not org_jurisdictions:
        return {"rules": [], "summary": {"total": 0, "conforming": 0, "partial": 0, "non_conforming": 0}}
    
    jurisdiction_ids = [j.id for j in org_jurisdictions]
    
    # Get compliance requirements for selected jurisdictions
    requirements_query = select(ComplianceRequirement).where(
        and_(
            ComplianceRequirement.jurisdiction_id.in_(jurisdiction_ids),
            ComplianceRequirement.is_active == True
        )
    ).join(Jurisdiction)
    
    # Apply regulation filter
    if regulation_filter and regulation_filter != "all":
        requirements_query = requirements_query.where(
            Jurisdiction.regulation_type == regulation_filter
        )
    
    # Apply severity filter
    if severity_filter and severity_filter != "all":
        requirements_query = requirements_query.where(
            ComplianceRequirement.criticality.ilike(f"%{severity_filter}%")
        )
    
    result = await db.execute(requirements_query.order_by(ComplianceRequirement.requirement_id))
    requirements = result.scalars().all()
    
    # Get assessments for these requirements
    assessments_result = await db.execute(
        select(ComplianceAssessment).where(
            and_(
                ComplianceAssessment.organization_id == organization.id,
                ComplianceAssessment.requirement_id.in_([r.id for r in requirements])
            )
        )
    )
    assessments = {a.requirement_id: a for a in assessments_result.scalars().all()}
    
    # Build rules list
    rules_list = []
    
    for requirement in requirements:
        assessment = assessments.get(requirement.id)
        
        # Determine status
        if assessment:
            status = assessment.status.lower()
            evidence = f"Evidence from assessment: {assessment.explanation or 'No explanation'}"
            last_updated = assessment.assessed_at.isoformat() if assessment.assessed_at else assessment.created_at.isoformat()
        else:
            status = "not_assessed"
            evidence = "No assessment completed"
            last_updated = requirement.created_at.isoformat()
        
        # Apply status filter
        if status_filter and status_filter != "all" and status != status_filter:
            continue
        
        rule = {
            "id": requirement.requirement_id,
            "title": requirement.title,
            "regulation": requirement.jurisdiction.name,
            "regulation_type": requirement.jurisdiction.regulation_type.value,
            "severity": requirement.criticality.lower(),
            "status": status,
            "description": requirement.description,
            "evidence": evidence,
            "page_number": requirement.page_number,
            "section_reference": requirement.section_reference,
            "category": requirement.category,
            "recommendation": assessment.gap_description if assessment else "Complete assessment to get recommendations",
            "confidence": 95 if assessment else 0,  # High confidence for extracted requirements
            "last_updated": last_updated
        }
        
        rules_list.append(rule)
    
    # Sort by severity and status
    def sort_key(rule):
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        status_order = {"non_compliant": 0, "partial": 1, "compliant": 2, "not_assessed": 3}
        return (
            severity_order.get(rule["severity"], 4),
            status_order.get(rule["status"], 4),
            -rule["confidence"]
        )
    
    rules_list.sort(key=sort_key)
    
    # Calculate summary
    summary = {
        "total": len(rules_list),
        "conforming": len([r for r in rules_list if r["status"] == "conform"]),
        "partial": len([r for r in rules_list if r["status"] == "partial"]),
        "non_conforming": len([r for r in rules_list if r["status"] == "non_conform"]),
        "high_severity": len([r for r in rules_list if r["severity"] == "high"])
    }
    
    return {
        "rules": rules_list,
        "summary": summary
    }


@router.get("/dashboard")
async def get_compliance_dashboard(
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization),
    db: AsyncSession = Depends(get_db)
):
    """Get compliance dashboard data"""
    
    # Ensure sample data exists
    jurisdictions_result = await db.execute(select(Jurisdiction))
    if not jurisdictions_result.first():
        await database_seeder.seed_jurisdictions(db)
        await database_seeder.create_sample_compliance_tasks(db, organization.id)
        await db.commit()
    
    # Get overall compliance stats
    compliance_results = await get_compliance_results(current_user, organization, db)
    
    # Get task statistics
    tasks_result = await db.execute(
        select(
            ComplianceTask.status,
            ComplianceTask.priority,
            func.count(ComplianceTask.id).label("count")
        ).where(
            ComplianceTask.organization_id == organization.id
        ).group_by(ComplianceTask.status, ComplianceTask.priority)
    )
    
    task_stats = {}
    for status, priority, count in tasks_result:
        if status.value not in task_stats:
            task_stats[status.value] = {"total": 0, "high": 0, "medium": 0, "low": 0}
        task_stats[status.value]["total"] += count
        task_stats[status.value][priority.value] += count
    
    # Get recent documents
    recent_docs_result = await db.execute(
        select(Document).where(
            Document.organization_id == organization.id
        ).order_by(Document.upload_date.desc()).limit(5)
    )
    
    recent_documents = []
    for doc in recent_docs_result.scalars():
        recent_documents.append({
            "id": str(doc.id),
            "filename": doc.filename,
            "upload_date": doc.upload_date.isoformat(),
            "document_type": doc.document_type.value
        })
    
    return {
        "compliance_summary": compliance_results["summary"],
        "task_statistics": task_stats,
        "recent_documents": recent_documents,
        "total_analyses": compliance_results["total_analyses"]
    }


@router.post("/assess-document")
async def assess_company_document(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None,
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization),
    db: AsyncSession = Depends(get_db)
):
    """Assess a company document against compliance requirements"""
    
    # Validate file format
    supported_extensions = ['.pdf', '.docx', '.doc', '.txt']
    file_ext = file.filename.lower().split('.')[-1] if '.' in file.filename else ''
    if f'.{file_ext}' not in supported_extensions:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file format. Supported formats: PDF, DOCX, DOC, TXT"
        )
    
    # Validate file size
    content = await file.read()
    max_size = getattr(settings, 'MAX_FILE_SIZE', 10 * 1024 * 1024)  # 10MB default
    if len(content) > max_size:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size: {max_size // 1024 // 1024}MB"
        )
    
    # Ensure upload directory exists
    upload_dir = getattr(settings, 'UPLOAD_DIR', 'uploads')
    assessment_dir = os.path.join(upload_dir, 'assessments')
    os.makedirs(assessment_dir, exist_ok=True)
    
    # Save file
    from datetime import datetime
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    safe_filename = f"{timestamp}_{file.filename}"
    file_path = os.path.join(assessment_dir, safe_filename)
    
    async with aiofiles.open(file_path, 'wb') as f:
        await f.write(content)
    
    try:
        # Perform assessment
        result = await document_assessor.assess_document(
            organization.id,
            file_path,
            file.filename,
            db,
            current_user.id
        )
        
        logger.info(f"Document assessment completed for {organization.name}: {result['overall_score']}%")
        
        return {
            "message": "Document assessment completed",
            "assessment_results": result
        }
        
    except Exception as e:
        logger.error(f"Document assessment failed: {e}")
        # Clean up uploaded file on error
        try:
            os.remove(file_path)
        except:
            pass
        raise HTTPException(
            status_code=500,
            detail=f"Assessment failed: {str(e)}"
        )


@router.get("/assessment-sessions")
async def get_assessment_sessions(
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization),
    db: AsyncSession = Depends(get_db)
):
    """Get all assessment sessions for the organization"""
    
    result = await db.execute(
        select(AssessmentSession)
        .where(AssessmentSession.organization_id == organization.id)
        .order_by(AssessmentSession.created_at.desc())
    )
    
    sessions = result.scalars().all()
    
    session_data = []
    for session in sessions:
        session_data.append({
            "id": str(session.id),
            "session_type": session.session_type,
            "source_document_name": session.source_document_name,
            "overall_score": session.overall_score,
            "total_requirements": session.total_requirements,
            "compliant_count": session.compliant_count,
            "partial_count": session.partial_count,
            "non_compliant_count": session.non_compliant_count,
            "not_addressed_count": session.not_addressed_count,
            "created_at": session.created_at.isoformat(),
            "completed_at": session.completed_at.isoformat() if session.completed_at else None
        })
    
    return {
        "sessions": session_data,
        "total_sessions": len(session_data)
    }


@router.get("/assessment-sessions/{session_id}")
async def get_assessment_session_details(
    session_id: UUID,
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization),
    db: AsyncSession = Depends(get_db)
):
    """Get detailed assessment results for a specific session"""
    
    # Get session
    session_result = await db.execute(
        select(AssessmentSession)
        .where(
            and_(
                AssessmentSession.id == session_id,
                AssessmentSession.organization_id == organization.id
            )
        )
    )
    session = session_result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(status_code=404, detail="Assessment session not found")
    
    # Get detailed assessments with requirement info
    assessments_result = await db.execute(
        select(ComplianceAssessment, ComplianceRequirement, Jurisdiction)
        .join(ComplianceRequirement)
        .join(Jurisdiction)
        .where(ComplianceAssessment.session_id == session_id)
        .order_by(ComplianceAssessment.created_at)
    )
    
    assessments = []
    for assessment, requirement, jurisdiction in assessments_result:
        assessments.append({
            "id": str(assessment.id),
            "requirement": {
                "id": str(requirement.id),
                "requirement_id": requirement.requirement_id,
                "title": requirement.title,
                "description": requirement.description,
                "category": requirement.category,
                "criticality": requirement.criticality
            },
            "jurisdiction": {
                "name": jurisdiction.name,
                "regulation_type": jurisdiction.regulation_type.value
            },
            "status": assessment.status,
            "evidence_text": assessment.evidence_text,
            "gap_description": assessment.gap_description,
            "recommendation": assessment.recommendation,
            "confidence_score": assessment.confidence_score,
            "assessed_at": assessment.assessed_at.isoformat() if assessment.assessed_at else None
        })
    
    return {
        "session": {
            "id": str(session.id),
            "session_type": session.session_type,
            "source_document_name": session.source_document_name,
            "overall_score": session.overall_score,
            "total_requirements": session.total_requirements,
            "compliant_count": session.compliant_count,
            "partial_count": session.partial_count,
            "non_compliant_count": session.non_compliant_count,
            "not_addressed_count": session.not_addressed_count,
            "created_at": session.created_at.isoformat(),
            "completed_at": session.completed_at.isoformat() if session.completed_at else None
        },
        "assessments": assessments,
        "summary": {
            "total_assessments": len(assessments),
            "by_status": {
                "compliant": session.compliant_count,
                "partial": session.partial_count,
                "non_compliant": session.non_compliant_count,
                "not_addressed": session.not_addressed_count
            },
            "by_criticality": self._calculate_criticality_breakdown(assessments)
        }
    }


def _calculate_criticality_breakdown(assessments: List[Dict]) -> Dict[str, int]:
    """Calculate breakdown by criticality level"""
    breakdown = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    
    for assessment in assessments:
        criticality = assessment.get("requirement", {}).get("criticality", "MEDIUM")
        if criticality in breakdown:
            breakdown[criticality] += 1
    
    return breakdown


@router.get("/generate-questionnaire/{jurisdiction_id}")
async def generate_questionnaire(
    jurisdiction_id: int,
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization),
    db: AsyncSession = Depends(get_db)
):
    """Generate dynamic questionnaire for compliance assessment"""
    
    try:
        # Verify user has access to this jurisdiction
        jurisdiction_result = await db.execute(
            select(Jurisdiction)
            .join(OrganizationJurisdiction)
            .where(
                and_(
                    Jurisdiction.id == jurisdiction_id,
                    OrganizationJurisdiction.organization_id == organization.id
                )
            )
        )
        jurisdiction = jurisdiction_result.scalar_one_or_none()
        
        if not jurisdiction:
            raise HTTPException(
                status_code=404, 
                detail="Jurisdiction not found or not accessible"
            )
        
        questionnaire_data = await form_generator.generate_questionnaire(
            db,
            jurisdiction_id
        )
        
        return {
            "message": "Questionnaire generated successfully",
            "questionnaire": questionnaire_data,
            "jurisdiction": {
                "id": jurisdiction.id,
                "name": jurisdiction.name,
                "regulation_type": jurisdiction.regulation_type.value
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate questionnaire: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Questionnaire generation failed: {str(e)}"
        )


@router.post("/submit-questionnaire/{jurisdiction_id}")
async def submit_questionnaire(
    jurisdiction_id: int,
    submission_data: Dict[str, Any],
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization),
    db: AsyncSession = Depends(get_db)
):
    """Submit completed compliance questionnaire"""
    
    try:
        # Validate submission data structure
        if not submission_data.get('responses') or not submission_data.get('questionnaire_data'):
            raise HTTPException(
                status_code=400,
                detail="Invalid submission data. Missing responses or questionnaire_data."
            )
        
        # Verify user has access to this jurisdiction  
        jurisdiction_result = await db.execute(
            select(Jurisdiction)
            .join(OrganizationJurisdiction)
            .where(
                and_(
                    Jurisdiction.id == jurisdiction_id,
                    OrganizationJurisdiction.organization_id == organization.id
                )
            )
        )
        jurisdiction = jurisdiction_result.scalar_one_or_none()
        
        if not jurisdiction:
            raise HTTPException(
                status_code=404, 
                detail="Jurisdiction not found or not accessible"
            )
        
        # Process questionnaire submission
        result = await form_generator.process_questionnaire_submission(
            db,
            current_user.id,
            jurisdiction_id,
            submission_data['responses'],
            submission_data['questionnaire_data']
        )
        
        logger.info(f"Questionnaire assessment completed for {organization.name}: {result['overall_score']}%")
        
        return {
            "message": "Questionnaire assessment completed successfully",
            "assessment_results": result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to process questionnaire submission: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Questionnaire submission failed: {str(e)}"
        )