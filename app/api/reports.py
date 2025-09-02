from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from app.database import get_db
from app.api.deps import get_current_user, get_current_verified_user, get_user_organization
from app.models.user import User
from app.models.organization import Organization
from app.models.document import Document, DocumentAnalysis, AnalysisStatus
from app.models.compliance import ComplianceTask, TaskStatus, TaskPriority
from app.models.jurisdiction import Jurisdiction
from app.services.report_generator import get_report_generator
from typing import List, Optional
from uuid import UUID
from datetime import datetime, timedelta
import json
import logging
import io

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/dashboard")
async def get_dashboard_stats(
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization),
    db: AsyncSession = Depends(get_db)
):
    """Get comprehensive dashboard statistics"""
    
    # Document statistics
    doc_total_result = await db.execute(
        select(func.count(Document.id)).where(
            Document.organization_id == organization.id
        )
    )
    total_documents = doc_total_result.scalar() or 0
    
    # Document analysis status breakdown
    doc_analysis_result = await db.execute(
        select(
            DocumentAnalysis.status,
            func.count(DocumentAnalysis.id).label("count")
        ).join(Document).where(
            Document.organization_id == organization.id
        ).group_by(DocumentAnalysis.status)
    )
    
    analysis_stats = {}
    for status, count in doc_analysis_result:
        analysis_stats[status.value] = count
    
    # Task statistics
    task_status_result = await db.execute(
        select(
            ComplianceTask.status,
            func.count(ComplianceTask.id).label("count")
        ).where(
            ComplianceTask.organization_id == organization.id
        ).group_by(ComplianceTask.status)
    )
    
    task_stats = {}
    total_tasks = 0
    for status, count in task_status_result:
        task_stats[status.value] = count
        total_tasks += count
    
    # Priority breakdown
    priority_result = await db.execute(
        select(
            ComplianceTask.priority,
            func.count(ComplianceTask.id).label("count")
        ).where(
            ComplianceTask.organization_id == organization.id
        ).group_by(ComplianceTask.priority)
    )
    
    priority_stats = {}
    for priority, count in priority_result:
        priority_stats[priority.value] = count
    
    # Overdue tasks
    overdue_result = await db.execute(
        select(func.count(ComplianceTask.id)).where(
            and_(
                ComplianceTask.organization_id == organization.id,
                ComplianceTask.due_date < datetime.utcnow(),
                ComplianceTask.status.in_([TaskStatus.TODO, TaskStatus.IN_PROGRESS])
            )
        )
    )
    overdue_tasks = overdue_result.scalar() or 0
    
    # Compliance score calculation
    completed_analyses = await db.execute(
        select(DocumentAnalysis.result).join(Document).where(
            and_(
                Document.organization_id == organization.id,
                DocumentAnalysis.status == AnalysisStatus.COMPLETED,
                DocumentAnalysis.result.isnot(None)
            )
        )
    )
    
    total_compliance_score = 0
    score_count = 0
    
    for analysis in completed_analyses.scalars():
        if analysis and "summary" in analysis:
            summary = analysis["summary"]
            conforming = summary.get("conforming", 0)
            partial = summary.get("partial", 0)
            total_rules = summary.get("conforming", 0) + summary.get("partial", 0) + summary.get("non_conforming", 0)
            
            if total_rules > 0:
                score = (conforming * 100 + partial * 50) / total_rules
                total_compliance_score += score
                score_count += 1
    
    average_compliance_score = round(total_compliance_score / score_count, 1) if score_count > 0 else 0
    
    # Recent activity (last 7 days)
    week_ago = datetime.utcnow() - timedelta(days=7)
    
    recent_docs = await db.execute(
        select(func.count(Document.id)).where(
            and_(
                Document.organization_id == organization.id,
                Document.upload_date >= week_ago
            )
        )
    )
    
    recent_tasks = await db.execute(
        select(func.count(ComplianceTask.id)).where(
            and_(
                ComplianceTask.organization_id == organization.id,
                ComplianceTask.created_at >= week_ago
            )
        )
    )
    
    return {
        "overview": {
            "total_documents": total_documents,
            "total_tasks": total_tasks,
            "overdue_tasks": overdue_tasks,
            "compliance_score": average_compliance_score
        },
        "document_analysis": analysis_stats,
        "task_status": task_stats,
        "task_priority": priority_stats,
        "recent_activity": {
            "documents_this_week": recent_docs.scalar() or 0,
            "tasks_created_this_week": recent_tasks.scalar() or 0
        }
    }


@router.get("/compliance-trends")
async def get_compliance_trends(
    days: int = Query(30, description="Number of days to analyze"),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization),
    db: AsyncSession = Depends(get_db)
):
    """Get compliance trends over time"""
    
    start_date = datetime.utcnow() - timedelta(days=days)
    
    # Get completed analyses over time
    analyses_result = await db.execute(
        select(
            DocumentAnalysis.completed_at,
            DocumentAnalysis.result
        ).join(Document).where(
            and_(
                Document.organization_id == organization.id,
                DocumentAnalysis.status == AnalysisStatus.COMPLETED,
                DocumentAnalysis.completed_at >= start_date,
                DocumentAnalysis.result.isnot(None)
            )
        ).order_by(DocumentAnalysis.completed_at.asc())
    )
    
    trend_data = []
    for completed_at, result in analyses_result:
        if result and "summary" in result:
            summary = result["summary"]
            conforming = summary.get("conforming", 0)
            partial = summary.get("partial", 0)
            non_conforming = summary.get("non_conforming", 0)
            total_rules = conforming + partial + non_conforming
            
            if total_rules > 0:
                score = (conforming * 100 + partial * 50) / total_rules
                trend_data.append({
                    "date": completed_at.isoformat(),
                    "compliance_score": round(score, 1),
                    "total_rules": total_rules,
                    "conforming": conforming,
                    "partial": partial,
                    "non_conforming": non_conforming
                })
    
    return {
        "period_days": days,
        "trend_data": trend_data,
        "total_analyses": len(trend_data)
    }


@router.get("/jurisdiction-breakdown")
async def get_jurisdiction_breakdown(
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization),
    db: AsyncSession = Depends(get_db)
):
    """Get breakdown of compliance by jurisdiction"""
    
    # Get task counts by jurisdiction
    jurisdiction_result = await db.execute(
        select(
            Jurisdiction.name,
            Jurisdiction.code,
            ComplianceTask.status,
            func.count(ComplianceTask.id).label("count")
        ).join(ComplianceTask).where(
            ComplianceTask.organization_id == organization.id
        ).group_by(Jurisdiction.name, Jurisdiction.code, ComplianceTask.status)
    )
    
    jurisdiction_data = {}
    for name, code, status, count in jurisdiction_result:
        if code not in jurisdiction_data:
            jurisdiction_data[code] = {
                "name": name,
                "code": code,
                "tasks": {"pending": 0, "in_progress": 0, "completed": 0, "cancelled": 0},
                "total_tasks": 0
            }
        
        jurisdiction_data[code]["tasks"][status.value] = count
        jurisdiction_data[code]["total_tasks"] += count
    
    return {
        "jurisdictions": list(jurisdiction_data.values())
    }


@router.get("/export-data")
async def export_compliance_data(
    format: str = Query("json", description="Export format: json, csv"),
    include_documents: bool = Query(True),
    include_tasks: bool = Query(True),
    include_analyses: bool = Query(True),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization),
    db: AsyncSession = Depends(get_db)
):
    """Export compliance data for the organization"""
    
    export_data = {
        "organization": {
            "name": organization.name,
            "id": str(organization.id),
            "exported_at": datetime.utcnow().isoformat()
        }
    }
    
    if include_documents:
        # Get documents
        docs_result = await db.execute(
            select(Document).where(
                Document.organization_id == organization.id
            ).order_by(Document.upload_date.desc())
        )
        
        documents = []
        for doc in docs_result.scalars():
            documents.append({
                "id": str(doc.id),
                "filename": doc.filename,
                "document_type": doc.document_type.value,
                "file_size": doc.file_size,
                "upload_date": doc.upload_date.isoformat(),
                "description": doc.description
            })
        
        export_data["documents"] = documents
    
    if include_tasks:
        # Get tasks
        tasks_result = await db.execute(
            select(ComplianceTask).where(
                ComplianceTask.organization_id == organization.id
            ).order_by(ComplianceTask.created_at.desc())
        )
        
        tasks = []
        for task in tasks_result.scalars():
            tasks.append({
                "id": str(task.id),
                "title": task.title,
                "description": task.description,
                "status": task.status.value,
                "priority": task.priority.value,
                "due_date": task.due_date.isoformat() if task.due_date else None,
                "estimated_hours": task.estimated_hours,
                "actual_hours": task.actual_hours,
                "completion_percentage": task.completion_percentage,
                "created_at": task.created_at.isoformat()
            })
        
        export_data["tasks"] = tasks
    
    if include_analyses:
        # Get analyses
        analyses_result = await db.execute(
            select(DocumentAnalysis).join(Document).where(
                and_(
                    Document.organization_id == organization.id,
                    DocumentAnalysis.status == AnalysisStatus.COMPLETED
                )
            ).order_by(DocumentAnalysis.completed_at.desc())
        )
        
        analyses = []
        for analysis in analyses_result.scalars():
            analyses.append({
                "id": str(analysis.id),
                "document_id": str(analysis.document_id),
                "analysis_type": analysis.analysis_type,
                "status": analysis.status.value,
                "result": analysis.result,
                "completed_at": analysis.completed_at.isoformat() if analysis.completed_at else None
            })
        
        export_data["analyses"] = analyses
    
    if format == "csv":
        # For CSV, return structured data that can be converted
        return {
            "format": "csv",
            "message": "CSV export functionality would be implemented here",
            "data_summary": {
                "documents": len(export_data.get("documents", [])),
                "tasks": len(export_data.get("tasks", [])),
                "analyses": len(export_data.get("analyses", []))
            }
        }
    
    return export_data


@router.get("/generate-report")
async def generate_compliance_report(
    report_type: str = Query("comprehensive", description="Type of report: comprehensive, summary, gaps"),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization),
    db: AsyncSession = Depends(get_db)
):
    """Generate a comprehensive compliance report"""
    
    # Get dashboard stats
    dashboard_stats = await get_dashboard_stats(current_user, organization, db)
    
    # Get compliance trends (last 30 days)
    trends = await get_compliance_trends(30, current_user, organization, db)
    
    # Get jurisdiction breakdown
    jurisdiction_breakdown = await get_jurisdiction_breakdown(current_user, organization, db)
    
    # Get recent compliance gaps
    gaps_result = await db.execute(
        select(DocumentAnalysis.result).join(Document).where(
            and_(
                Document.organization_id == organization.id,
                DocumentAnalysis.status == AnalysisStatus.COMPLETED,
                DocumentAnalysis.result.isnot(None)
            )
        ).limit(10)
    )
    
    gaps = []
    for result in gaps_result.scalars():
        if result and "compliance_rules" in result:
            rules = result["compliance_rules"]
            for rule in rules:
                if rule.get("status") in ["partial", "non_conform"]:
                    gaps.append({
                        "rule_id": rule.get("rule_id"),
                        "rule_title": rule.get("rule_title"),
                        "status": rule.get("status"),
                        "severity": rule.get("severity", "medium"),
                        "explanation": rule.get("explanation"),
                        "recommendation": rule.get("recommendation")
                    })
    
    report_data = {
        "report_metadata": {
            "organization": organization.name,
            "report_type": report_type,
            "generated_at": datetime.utcnow().isoformat(),
            "generated_by": current_user.email
        },
        "executive_summary": {
            "overall_compliance_score": dashboard_stats["overview"]["compliance_score"],
            "total_documents_analyzed": dashboard_stats["overview"]["total_documents"],
            "total_compliance_tasks": dashboard_stats["overview"]["total_tasks"],
            "overdue_tasks": dashboard_stats["overview"]["overdue_tasks"],
            "critical_gaps_count": len([g for g in gaps if g.get("severity") == "high"])
        },
        "detailed_analytics": dashboard_stats,
        "compliance_trends": trends,
        "jurisdiction_analysis": jurisdiction_breakdown,
        "compliance_gaps": gaps[:10],  # Top 10 gaps
        "recommendations": [
            {
                "priority": "high",
                "title": "Address Overdue Tasks",
                "description": f"There are {dashboard_stats['overview']['overdue_tasks']} overdue compliance tasks that require immediate attention."
            },
            {
                "priority": "medium", 
                "title": "Improve Documentation",
                "description": "Consider implementing automated compliance monitoring to reduce manual oversight burden."
            },
            {
                "priority": "low",
                "title": "Regular Review Cycle",
                "description": "Establish quarterly compliance reviews to maintain high compliance scores."
            }
        ]
    }
    
    return report_data


@router.get("/export")
async def export_compliance_report(
    format: str = Query("json", description="Export format: json, csv, pdf"),
    report_type: str = Query("comprehensive", description="Type of report"),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization),
    db: AsyncSession = Depends(get_db)
):
    """Export compliance report in various formats"""
    
    try:
        # Get report generator
        report_generator = await get_report_generator(db, organization)
        
        # Generate report
        report_result = await report_generator.generate_compliance_report(
            report_type=report_type,
            format=format
        )
        
        if format == "json":
            return report_result
        elif format in ["csv", "pdf"]:
            # Return file download
            content = report_result["content"]
            content_type = report_result["content_type"]
            filename = report_result["filename"]
            
            if format == "csv":
                return Response(
                    content=content,
                    media_type=content_type,
                    headers={"Content-Disposition": f"attachment; filename={filename}"}
                )
            elif format == "pdf":
                return Response(
                    content=content,
                    media_type=content_type,
                    headers={"Content-Disposition": f"attachment; filename={filename}"}
                )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported format: {format}"
            )
    
    except Exception as e:
        logger.error(f"Error generating export: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate report: {str(e)}"
        )


@router.post("/generate-custom-report")
async def generate_custom_report(
    report_config: dict,
    format: str = Query("json", description="Export format: json, csv, pdf"),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization),
    db: AsyncSession = Depends(get_db)
):
    """Generate a custom report based on specific configuration"""
    
    try:
        # Get report generator
        report_generator = await get_report_generator(db, organization)
        
        # Generate custom report (would need to extend ReportGenerator for this)
        report_result = await report_generator.generate_compliance_report(
            report_type="custom",
            format=format
        )
        
        return report_result
    
    except Exception as e:
        logger.error(f"Error generating custom report: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate custom report: {str(e)}"
        )