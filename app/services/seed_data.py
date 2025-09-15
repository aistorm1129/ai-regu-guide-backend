"""Database seed data for jurisdictions and compliance rules"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.jurisdiction import Jurisdiction, RegulationType
from app.models.organization import Organization, OrganizationSize
from app.models.compliance import ComplianceTask
from app.models.user import User
from datetime import datetime, timedelta
import uuid
import logging

logger = logging.getLogger(__name__)

class DatabaseSeeder:
    
    @staticmethod
    async def seed_jurisdictions(db: AsyncSession):
        """Seed jurisdiction data"""
        
        # Check if jurisdictions already exist
        result = await db.execute(select(Jurisdiction))
        if result.first():
            logger.info("Jurisdictions already seeded")
            return
        
        jurisdictions_data = [
            {
                "name": "EU AI Act",
                "code": "EU-AI-ACT",
                "description": "European Union Artificial Intelligence Act - Comprehensive AI regulation framework",
                "regulation_type": RegulationType.EU_AI_ACT,
                "effective_date": datetime(2024, 8, 1),
                "compliance_requirements": [
                    "High-Risk AI System Registration",
                    "Algorithm Bias Testing Requirements", 
                    "Human Oversight Implementation",
                    "Transparency and Explainability",
                    "Data Governance and Quality",
                    "Risk Assessment Documentation",
                    "Conformity Assessment Procedures",
                    "Post-Market Monitoring",
                    "CE Marking Requirements",
                    "Technical Documentation"
                ],
                "rules": {
                    "prohibited_practices": [
                        "Subliminal techniques beyond person's consciousness",
                        "Exploiting vulnerabilities of specific groups",
                        "Social scoring by public authorities",
                        "Real-time biometric identification in public spaces"
                    ],
                    "high_risk_systems": [
                        "Biometric identification and categorization",
                        "Management of critical infrastructure", 
                        "Education and vocational training",
                        "Employment and worker management",
                        "Essential services access",
                        "Law enforcement",
                        "Migration and asylum",
                        "Administration of justice"
                    ]
                }
            },
            {
                "name": "US AI Governance",
                "code": "US-AI-GOV",
                "description": "NIST AI Framework and Executive Orders on AI safety and security",
                "regulation_type": RegulationType.US_AI_GOVERNANCE,
                "effective_date": datetime(2023, 10, 30),
                "compliance_requirements": [
                    "AI Risk Management Framework Implementation",
                    "Executive Order Compliance",
                    "Algorithmic Impact Assessments",
                    "Federal AI Use Case Reporting",
                    "AI Safety and Security Standards",
                    "Privacy-Preserving Techniques",
                    "Bias Mitigation Strategies",
                    "Human-AI Configuration",
                    "AI System Testing and Evaluation",
                    "Performance Monitoring"
                ],
                "rules": {
                    "nist_functions": [
                        "GOVERN: Establish AI governance",
                        "MAP: Categorize AI risks and impacts", 
                        "MEASURE: Assess AI risks and impacts",
                        "MANAGE: Allocate resources to AI risks"
                    ],
                    "executive_order": [
                        "Establish AI safety and security standards",
                        "Protect Americans' privacy",
                        "Advance equity and civil rights",
                        "Stand up for consumers and workers",
                        "Promote innovation and competition",
                        "Advance American leadership abroad"
                    ]
                }
            },
            {
                "name": "ISO/IEC 42001",
                "code": "ISO-42001",
                "description": "International standard for AI management systems",
                "regulation_type": RegulationType.ISO_42001,
                "effective_date": datetime(2023, 12, 18),
                "compliance_requirements": [
                    "AI Management System Framework",
                    "AI Policy Development",
                    "Risk Management Processes",
                    "AI Objectives and Planning",
                    "Resource Management",
                    "AI System Development Lifecycle",
                    "Operational Planning and Control",
                    "Performance Evaluation",
                    "Continuous Improvement",
                    "Management Review"
                ],
                "rules": {
                    "management_system": [
                        "Context of the organization",
                        "Leadership and commitment",
                        "AI management system policy",
                        "Organizational roles and responsibilities",
                        "Risk and opportunity management",
                        "AI objectives and planning",
                        "Resources and competence",
                        "Communication and documentation"
                    ],
                    "ai_lifecycle": [
                        "Planning and design",
                        "Data management",
                        "Model development",
                        "Verification and validation", 
                        "Implementation and deployment",
                        "Operation and monitoring",
                        "Maintenance and updates"
                    ]
                }
            }
        ]
        
        for jurisdiction_data in jurisdictions_data:
            # Transform the data to match the Jurisdiction model
            filtered_data = {
                "name": jurisdiction_data["name"],
                "description": jurisdiction_data["description"],
                "regulation_type": RegulationType.EU_AI_ACT if "EU" in jurisdiction_data["name"] else 
                                 RegulationType.US_AI_GOVERNANCE if "US" in jurisdiction_data["name"] else 
                                 RegulationType.ISO_42001 if "ISO" in jurisdiction_data["name"] else RegulationType.CUSTOM,
                "effective_date": jurisdiction_data.get("effective_date"),
                "requirements_data": {
                    "compliance_requirements": jurisdiction_data.get("compliance_requirements", []),
                    "rules": jurisdiction_data.get("rules", {})
                }
            }
            jurisdiction = Jurisdiction(**filtered_data)
            db.add(jurisdiction)
        
        await db.flush()
        logger.info(f"Seeded {len(jurisdictions_data)} jurisdictions")
    
    @staticmethod
    async def seed_sample_organization(db: AsyncSession, user_id: uuid.UUID):
        """Create a sample organization for a user"""
        
        # Check if user already has an organization
        result = await db.execute(
            select(Organization).join(Organization.users).where(User.id == user_id)
        )
        if result.first():
            logger.info("User already has an organization")
            return
        
        organization = Organization(
            name="Sample AI Company",
            description="A sample organization for AI compliance testing",
            industry="Technology",
            size=OrganizationSize.MEDIUM,
            country="United States"
        )
        
        db.add(organization)
        await db.flush()
        
        # Add user to organization
        from app.models.organization import UserOrganization
        user_org = UserOrganization(
            user_id=user_id,
            organization_id=organization.id,
            role="ADMIN"
        )
        db.add(user_org)
        
        logger.info(f"Created sample organization for user {user_id}")
        return organization
    
    @staticmethod
    async def create_sample_compliance_tasks(db: AsyncSession, organization_id: uuid.UUID):
        """Create sample compliance tasks"""
        
        # Get jurisdictions
        result = await db.execute(select(Jurisdiction))
        jurisdictions = result.scalars().all()
        
        if not jurisdictions:
            logger.warning("No jurisdictions found for creating tasks")
            return
        
        sample_tasks = [
            {
                "title": "Implement High-Risk AI System Registration",
                "description": "Register high-risk AI systems with the EU database as required by the AI Act",
                "jurisdiction_code": "EU-AI-ACT",
                "priority": "high",
                "status": "todo",
                "due_date": datetime.now() + timedelta(days=30),
                "estimated_hours": 40
            },
            {
                "title": "Conduct Algorithm Bias Testing",
                "description": "Perform comprehensive bias testing on AI algorithms to ensure fairness",
                "jurisdiction_code": "EU-AI-ACT", 
                "priority": "medium",
                "status": "in_progress",
                "due_date": datetime.now() + timedelta(days=45),
                "estimated_hours": 60
            },
            {
                "title": "Develop Human Oversight Procedures",
                "description": "Create and document human oversight procedures for AI decision-making",
                "jurisdiction_code": "EU-AI-ACT",
                "priority": "high",
                "status": "todo",
                "due_date": datetime.now() + timedelta(days=21),
                "estimated_hours": 30
            },
            {
                "title": "NIST AI Risk Management Framework Implementation",
                "description": "Implement NIST AI RMF across the organization",
                "jurisdiction_code": "US-AI-GOV",
                "priority": "medium", 
                "status": "todo",
                "due_date": datetime.now() + timedelta(days=60),
                "estimated_hours": 80
            },
            {
                "title": "AI Management System Documentation",
                "description": "Create comprehensive AI management system documentation per ISO/IEC 42001",
                "jurisdiction_code": "ISO-42001",
                "priority": "medium",
                "status": "in_progress", 
                "due_date": datetime.now() + timedelta(days=90),
                "estimated_hours": 100
            }
        ]
        
        for task_data in sample_tasks:
            jurisdiction_code = task_data.pop('jurisdiction_code')
            # Map jurisdiction codes to names
            jurisdiction_mapping = {
                "EU-AI-ACT": "EU AI Act",
                "US-AI-GOV": "US AI Governance", 
                "ISO-42001": "ISO/IEC 42001"
            }
            jurisdiction_name = jurisdiction_mapping.get(jurisdiction_code)
            jurisdiction = next((j for j in jurisdictions if j.name == jurisdiction_name), None)
            
            if jurisdiction:
                task = ComplianceTask(
                    organization_id=organization_id,
                    jurisdiction_id=jurisdiction.id,
                    **task_data
                )
                db.add(task)
        
        await db.flush()
        logger.info(f"Created {len(sample_tasks)} sample compliance tasks")

# Global instance
database_seeder = DatabaseSeeder()