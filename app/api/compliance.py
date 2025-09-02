from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from app.database import get_db
from app.api.deps import get_current_user, get_current_verified_user, get_user_organization
from app.models.user import User
from app.models.organization import Organization
from app.models.document import Document, DocumentAnalysis, AnalysisStatus
from app.models.jurisdiction import Jurisdiction, OrganizationJurisdiction
from app.models.compliance import ComplianceTask
from app.services.seed_data import database_seeder
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
    """Get detailed compliance rules with their current status"""
    
    # Ensure sample data exists
    result = await db.execute(select(Jurisdiction))
    if not result.first():
        await database_seeder.seed_jurisdictions(db)
        await db.commit()
    
    # Get all completed analyses for the organization
    result = await db.execute(
        select(DocumentAnalysis).join(Document).where(
            and_(
                Document.organization_id == organization.id,
                DocumentAnalysis.status == AnalysisStatus.COMPLETED
            )
        )
    )
    
    analyses = result.scalars().all()
    
    # Collect all rules from analyses
    all_rules = {}
    
    for analysis in analyses:
        if analysis.result and "compliance_rules" in analysis.result:
            rules = analysis.result["compliance_rules"]
            
            for rule in rules:
                rule_id = rule.get("rule_id")
                if rule_id:
                    # Use the most recent analysis for each rule
                    if rule_id not in all_rules or analysis.completed_at > all_rules[rule_id].get("last_updated", analysis.completed_at):
                        all_rules[rule_id] = {
                            "id": rule_id,
                            "title": rule.get("rule_title", ""),
                            "regulation": rule_id.split("-")[0] if "-" in rule_id else "Unknown",
                            "severity": rule.get("severity", "medium"),
                            "status": rule.get("status", "unknown"),
                            "description": rule.get("explanation", ""),
                            "evidence": rule.get("evidence", "No evidence found"),
                            "recommendation": rule.get("recommendation", ""),
                            "confidence": rule.get("confidence", 0),
                            "last_updated": analysis.completed_at.isoformat()
                        }
    
    # Convert to list and apply filters
    rules_list = list(all_rules.values())
    
    if regulation_filter and regulation_filter != "all":
        rules_list = [r for r in rules_list if r["regulation"].lower() == regulation_filter.lower()]
    
    if status_filter and status_filter != "all":
        rules_list = [r for r in rules_list if r["status"] == status_filter]
    
    if severity_filter and severity_filter != "all":
        rules_list = [r for r in rules_list if r["severity"] == severity_filter]
    
    # Sort by severity and status
    def sort_key(rule):
        severity_order = {"high": 0, "medium": 1, "low": 2}
        status_order = {"non_conform": 0, "partial": 1, "conform": 2}
        return (
            severity_order.get(rule["severity"], 3),
            status_order.get(rule["status"], 3),
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