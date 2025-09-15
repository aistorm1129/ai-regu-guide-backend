#!/usr/bin/env python3
"""
Add sample compliance requirements for testing
"""

import asyncio
import sys
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.jurisdiction import Jurisdiction, RegulationType
from app.models.compliance import ComplianceRequirement
from app.services.seed_data import database_seeder


async def add_sample_requirements():
    """Add sample compliance requirements for testing"""
    
    async for db in get_db():
        try:
            # Ensure jurisdictions exist
            result = await db.execute(select(Jurisdiction))
            jurisdictions = result.scalars().all()
            
            if not jurisdictions:
                print("No jurisdictions found, seeding...")
                await database_seeder.seed_jurisdictions(db)
                await db.commit()
                
                # Re-fetch jurisdictions
                result = await db.execute(select(Jurisdiction))
                jurisdictions = result.scalars().all()
            
            print(f"Found {len(jurisdictions)} jurisdictions")
            
            # Find US AI Governance jurisdiction
            us_jurisdiction = None
            for j in jurisdictions:
                if j.regulation_type == RegulationType.US_AI_GOVERNANCE:
                    us_jurisdiction = j
                    break
            
            if not us_jurisdiction:
                print("US AI Governance jurisdiction not found")
                return
            
            print(f"Found US jurisdiction: {us_jurisdiction.name}")
            
            # Check if requirements already exist
            existing_reqs = await db.execute(
                select(ComplianceRequirement).where(
                    ComplianceRequirement.jurisdiction_id == us_jurisdiction.id
                )
            )
            if existing_reqs.scalars().first():
                print("Sample requirements already exist")
                return
            
            # Add sample US AI Governance requirements
            sample_requirements = [
                {
                    "requirement_id": "NIST-GOVERN-1.1",
                    "title": "AI Governance Structure",
                    "description": "Establish organizational governance for AI risk management",
                    "category": "GOVERN",
                    "criticality": "HIGH",
                    "section_reference": "GOVERN-1.1",
                    "page_number": 15
                },
                {
                    "requirement_id": "NIST-MAP-1.1", 
                    "title": "AI System Context Mapping",
                    "description": "Document the context and business value of AI systems",
                    "category": "MAP",
                    "criticality": "MEDIUM",
                    "section_reference": "MAP-1.1", 
                    "page_number": 22
                },
                {
                    "requirement_id": "NIST-MEASURE-2.1",
                    "title": "AI Risk Assessment",
                    "description": "Conduct comprehensive risk assessments for AI systems",
                    "category": "MEASURE",
                    "criticality": "HIGH",
                    "section_reference": "MEASURE-2.1",
                    "page_number": 35
                },
                {
                    "requirement_id": "NIST-MANAGE-1.1",
                    "title": "Risk Response Planning",
                    "description": "Develop and implement risk response plans for AI systems",
                    "category": "MANAGE", 
                    "criticality": "HIGH",
                    "section_reference": "MANAGE-1.1",
                    "page_number": 45
                },
                {
                    "requirement_id": "EO-14110-1",
                    "title": "AI Safety Testing",
                    "description": "Implement safety testing for AI models before deployment",
                    "category": "GOVERN",
                    "criticality": "CRITICAL",
                    "section_reference": "Section 4.1",
                    "page_number": 8
                }
            ]
            
            for req_data in sample_requirements:
                requirement = ComplianceRequirement(
                    jurisdiction_id=us_jurisdiction.id,
                    **req_data
                )
                db.add(requirement)
                print(f"Added requirement: {req_data['title']}")
            
            await db.commit()
            print(f"Successfully added {len(sample_requirements)} sample requirements")
            
        except Exception as e:
            print(f"Error: {e}")
            await db.rollback()
            
        break


if __name__ == "__main__":
    asyncio.run(add_sample_requirements())