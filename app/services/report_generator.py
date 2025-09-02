import io
import csv
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import joinedload

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

from app.models.organization import Organization
from app.models.jurisdiction import Jurisdiction, OrganizationJurisdiction
from app.models.compliance import ComplianceTask, ComplianceReport
from app.models.document import Document, DocumentAnalysis
from app.models.form_question import FormResponse


class ReportGenerator:
    def __init__(self, db: AsyncSession, organization: Organization):
        self.db = db
        self.organization = organization
    
    async def generate_compliance_report(
        self,
        report_type: str = "comprehensive",
        format: str = "json"
    ) -> Dict[str, Any]:
        """Generate a comprehensive compliance report"""
        
        # Gather all compliance data
        data = await self._gather_compliance_data()
        
        if format == "csv":
            return await self._generate_csv_report(data)
        elif format == "pdf" and REPORTLAB_AVAILABLE:
            return await self._generate_pdf_report(data, report_type)
        elif format == "json":
            return data
        else:
            raise ValueError(f"Unsupported format: {format}")
    
    async def _gather_compliance_data(self) -> Dict[str, Any]:
        """Gather all compliance-related data for the organization"""
        
        # Get organization jurisdictions
        jurisdictions_result = await self.db.execute(
            select(Jurisdiction)
            .join(OrganizationJurisdiction)
            .where(OrganizationJurisdiction.organization_id == self.organization.id)
        )
        jurisdictions = jurisdictions_result.scalars().all()
        
        # Get compliance tasks
        tasks_result = await self.db.execute(
            select(ComplianceTask)
            .where(ComplianceTask.organization_id == self.organization.id)
            .order_by(ComplianceTask.created_at.desc())
        )
        tasks = tasks_result.scalars().all()
        
        # Get documents
        documents_result = await self.db.execute(
            select(Document)
            .options(joinedload(Document.analysis))
            .where(Document.organization_id == self.organization.id)
            .order_by(Document.upload_date.desc())
        )
        documents = documents_result.scalars().all()
        
        # Get form responses
        form_responses_result = await self.db.execute(
            select(FormResponse)
            .options(joinedload(FormResponse.question))
            .where(FormResponse.organization_id == self.organization.id)
            .order_by(FormResponse.created_at.desc())
        )
        form_responses = form_responses_result.scalars().all()
        
        # Calculate compliance statistics
        total_tasks = len(tasks)
        completed_tasks = sum(1 for task in tasks if task.status == 'completed')
        pending_tasks = sum(1 for task in tasks if task.status == 'pending')
        in_progress_tasks = sum(1 for task in tasks if task.status == 'in_progress')
        
        compliance_score = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
        
        return {
            "organization": {
                "id": str(self.organization.id),
                "name": self.organization.name,
                "description": self.organization.description
            },
            "report_metadata": {
                "generated_at": datetime.utcnow().isoformat(),
                "report_type": "comprehensive",
                "total_jurisdictions": len(jurisdictions),
                "total_documents": len(documents),
                "total_tasks": total_tasks,
                "total_form_responses": len(form_responses)
            },
            "compliance_summary": {
                "overall_score": round(compliance_score, 2),
                "completed_tasks": completed_tasks,
                "pending_tasks": pending_tasks,
                "in_progress_tasks": in_progress_tasks,
                "total_tasks": total_tasks
            },
            "jurisdictions": [
                {
                    "id": str(jurisdiction.id),
                    "name": jurisdiction.name,
                    "code": jurisdiction.code,
                    "description": jurisdiction.description,
                    "is_active": jurisdiction.is_active
                }
                for jurisdiction in jurisdictions
            ],
            "tasks": [
                {
                    "id": str(task.id),
                    "title": task.title,
                    "description": task.description,
                    "status": task.status,
                    "priority": task.priority,
                    "due_date": task.due_date.isoformat() if task.due_date else None,
                    "created_at": task.created_at.isoformat(),
                    "assigned_user": task.assigned_user.full_name if task.assigned_user else None
                }
                for task in tasks
            ],
            "documents": [
                {
                    "id": str(doc.id),
                    "filename": doc.filename,
                    "document_type": doc.document_type,
                    "file_size": doc.file_size,
                    "upload_date": doc.upload_date.isoformat(),
                    "analysis_status": doc.analysis.status if doc.analysis else None,
                    "analysis_summary": doc.analysis.summary if doc.analysis else None
                }
                for doc in documents
            ],
            "form_responses": [
                {
                    "question_id": str(response.question_id),
                    "question": response.question.question if response.question else None,
                    "category": response.question.category if response.question else None,
                    "answer": response.answer,
                    "created_at": response.created_at.isoformat()
                }
                for response in form_responses
            ]
        }
    
    async def _generate_csv_report(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate CSV format report"""
        
        # Create CSV buffer
        csv_buffer = io.StringIO()
        
        # Write summary section
        csv_buffer.write("# COMPLIANCE REPORT SUMMARY\n")
        csv_buffer.write(f"Organization,{data['organization']['name']}\n")
        csv_buffer.write(f"Generated At,{data['report_metadata']['generated_at']}\n")
        csv_buffer.write(f"Overall Compliance Score,{data['compliance_summary']['overall_score']}%\n")
        csv_buffer.write(f"Total Tasks,{data['compliance_summary']['total_tasks']}\n")
        csv_buffer.write(f"Completed Tasks,{data['compliance_summary']['completed_tasks']}\n")
        csv_buffer.write(f"Pending Tasks,{data['compliance_summary']['pending_tasks']}\n")
        csv_buffer.write("\n")
        
        # Write jurisdictions section
        csv_buffer.write("# JURISDICTIONS\n")
        if data['jurisdictions']:
            writer = csv.DictWriter(csv_buffer, fieldnames=['name', 'code', 'description', 'is_active'])
            writer.writeheader()
            writer.writerows(data['jurisdictions'])
        csv_buffer.write("\n")
        
        # Write tasks section
        csv_buffer.write("# COMPLIANCE TASKS\n")
        if data['tasks']:
            writer = csv.DictWriter(csv_buffer, fieldnames=['title', 'status', 'priority', 'due_date', 'assigned_user'])
            writer.writeheader()
            writer.writerows(data['tasks'])
        csv_buffer.write("\n")
        
        # Write documents section
        csv_buffer.write("# DOCUMENTS\n")
        if data['documents']:
            writer = csv.DictWriter(csv_buffer, fieldnames=['filename', 'document_type', 'upload_date', 'analysis_status'])
            writer.writeheader()
            writer.writerows(data['documents'])
        
        csv_content = csv_buffer.getvalue()
        csv_buffer.close()
        
        return {
            "content": csv_content,
            "content_type": "text/csv",
            "filename": f"compliance_report_{data['organization']['name']}_{datetime.now().strftime('%Y%m%d')}.csv"
        }
    
    async def _generate_pdf_report(self, data: Dict[str, Any], report_type: str) -> Dict[str, Any]:
        """Generate PDF format report"""
        
        if not REPORTLAB_AVAILABLE:
            raise ValueError("PDF generation requires reportlab package")
        
        # Create PDF buffer
        pdf_buffer = io.BytesIO()
        
        # Create document
        doc = SimpleDocTemplate(pdf_buffer, pagesize=A4)
        elements = []
        
        # Get styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            spaceAfter=30,
            textColor=colors.HexColor('#1f2937')
        )
        
        # Title
        elements.append(Paragraph("AI Compliance Report", title_style))
        elements.append(Spacer(1, 20))
        
        # Organization info
        org_info = [
            ["Organization:", data['organization']['name']],
            ["Generated:", data['report_metadata']['generated_at'][:16]],
            ["Report Type:", report_type.title()],
            ["Overall Compliance Score:", f"{data['compliance_summary']['overall_score']}%"]
        ]
        
        org_table = Table(org_info, colWidths=[2*inch, 3*inch])
        org_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 12),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ]))
        elements.append(org_table)
        elements.append(Spacer(1, 20))
        
        # Compliance Summary
        elements.append(Paragraph("Compliance Summary", styles['Heading2']))
        summary_data = [
            ["Metric", "Count", "Percentage"],
            ["Completed Tasks", str(data['compliance_summary']['completed_tasks']), 
             f"{(data['compliance_summary']['completed_tasks'] / data['compliance_summary']['total_tasks'] * 100):.1f}%" if data['compliance_summary']['total_tasks'] > 0 else "0%"],
            ["In Progress Tasks", str(data['compliance_summary']['in_progress_tasks']), 
             f"{(data['compliance_summary']['in_progress_tasks'] / data['compliance_summary']['total_tasks'] * 100):.1f}%" if data['compliance_summary']['total_tasks'] > 0 else "0%"],
            ["Pending Tasks", str(data['compliance_summary']['pending_tasks']), 
             f"{(data['compliance_summary']['pending_tasks'] / data['compliance_summary']['total_tasks'] * 100):.1f}%" if data['compliance_summary']['total_tasks'] > 0 else "0%"],
            ["Total Tasks", str(data['compliance_summary']['total_tasks']), "100%"],
        ]
        
        summary_table = Table(summary_data, colWidths=[2.5*inch, 1*inch, 1.5*inch])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        elements.append(summary_table)
        elements.append(Spacer(1, 20))
        
        # Jurisdictions
        if data['jurisdictions']:
            elements.append(Paragraph("Active Jurisdictions", styles['Heading2']))
            jurisdiction_data = [["Name", "Code", "Status"]]
            for jurisdiction in data['jurisdictions']:
                jurisdiction_data.append([
                    jurisdiction['name'],
                    jurisdiction['code'],
                    "Active" if jurisdiction['is_active'] else "Inactive"
                ])
            
            jurisdiction_table = Table(jurisdiction_data, colWidths=[2*inch, 1.5*inch, 1.5*inch])
            jurisdiction_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            elements.append(jurisdiction_table)
        
        # Build PDF
        doc.build(elements)
        
        pdf_content = pdf_buffer.getvalue()
        pdf_buffer.close()
        
        return {
            "content": pdf_content,
            "content_type": "application/pdf",
            "filename": f"compliance_report_{data['organization']['name']}_{datetime.now().strftime('%Y%m%d')}.pdf"
        }


# Global instance
async def get_report_generator(db: AsyncSession, organization: Organization) -> ReportGenerator:
    return ReportGenerator(db, organization)