"""
Service for assessing company documents against compliance requirements
"""

from typing import List, Dict, Any, Optional
from uuid import UUID
import logging
from datetime import datetime

from app.services.assistant_manager import assistant_manager
from app.services.document_processor import document_processor
from app.models.compliance import AssessmentSession, ComplianceAssessment
from app.models.jurisdiction import Jurisdiction
from app.models.compliance import ComplianceRequirement
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import uuid

logger = logging.getLogger(__name__)


class DocumentAssessor:
    """Assess company documents against compliance requirements"""
    
    async def assess_document(
        self,
        organization_id: UUID,
        document_path: str,
        document_name: str,
        db: AsyncSession,
        created_by: UUID
    ) -> Dict[str, Any]:
        """
        Assess a company document against all applicable compliance requirements
        """
        
        try:
            # Create assessment session
            session = AssessmentSession(
                organization_id=organization_id,
                session_type="document_upload",
                source_document_name=document_name,
                source_document_path=document_path,
                created_by=created_by
            )
            db.add(session)
            await db.flush()
            
            # Extract text from company document
            company_text, file_type = document_processor.extract_text_from_file(document_path, document_name)
            
            if file_type == 'error':
                raise Exception(f"Failed to extract text from {document_name}")
            
            # Get organization's compliance requirements
            requirements = await self._get_organization_requirements(organization_id, db)
            
            if not requirements:
                raise Exception("No compliance requirements found for organization")
            
            # Group requirements by jurisdiction for efficient processing
            jurisdiction_requirements = self._group_requirements_by_jurisdiction(requirements)
            
            all_assessments = []
            
            # Process each jurisdiction separately using its Assistant
            for jurisdiction_id, req_list in jurisdiction_requirements.items():
                
                # Get jurisdiction info
                jurisdiction = await self._get_jurisdiction(jurisdiction_id, db)
                
                if jurisdiction and jurisdiction.assistant_id:
                    # Use existing Assistant for this jurisdiction
                    logger.info(f"🤖 Using persistent Assistant {jurisdiction.assistant_id} for {jurisdiction.name}")
                    logger.info(f"📊 Assessing against {len(req_list)} requirements using Assistant API")

                    assessments = await assistant_manager.assess_document_against_requirements(
                        jurisdiction.assistant_id,
                        company_text,
                        req_list
                    )

                    if assessments:
                        logger.info(f"✅ Assistant API completed assessment: {len(assessments)} results")
                    else:
                        logger.warning(f"⚠️ Assistant API returned no assessments, using fallback")
                        assessments = await self._fallback_text_analysis(company_text, req_list)
                else:
                    # Fallback to direct text analysis
                    logger.warning(f"⚠️ No Assistant configured for jurisdiction {jurisdiction.name if jurisdiction else 'Unknown'}")
                    logger.info(f"📄 Using fallback text analysis for {len(req_list)} requirements")
                    assessments = await self._fallback_text_analysis(company_text, req_list)
                
                # Convert assessments to database objects
                for assessment_data in assessments:
                    assessment = await self._create_assessment_record(
                        session.id,
                        organization_id,
                        assessment_data,
                        req_list,
                        db
                    )
                    if assessment:
                        all_assessments.append(assessment)
            
            # Calculate overall scores
            overall_stats = self._calculate_overall_scores(all_assessments)
            
            # Update session with final scores
            session.total_requirements = overall_stats['total']
            session.compliant_count = overall_stats['compliant']
            session.partial_count = overall_stats['partial']
            session.non_compliant_count = overall_stats['non_compliant']
            session.not_addressed_count = overall_stats['not_addressed']
            session.overall_score = overall_stats['score']
            session.completed_at = datetime.utcnow()
            
            await db.commit()
            
            logger.info(f"Assessment completed: {overall_stats['score']}% compliance ({overall_stats['total']} requirements)")
            
            return {
                "session_id": str(session.id),
                "overall_score": overall_stats['score'],
                "total_requirements": overall_stats['total'],
                "compliant": overall_stats['compliant'],
                "partial": overall_stats['partial'],
                "non_compliant": overall_stats['non_compliant'],
                "not_addressed": overall_stats['not_addressed'],
                "assessments": [self._serialize_assessment(a) for a in all_assessments]
            }
            
        except Exception as e:
            logger.error(f"Failed to assess document {document_name}: {e}")
            await db.rollback()
            raise
    
    async def _get_organization_requirements(self, organization_id: UUID, db: AsyncSession) -> List[Dict[str, Any]]:
        """Get all compliance requirements for an organization"""
        
        # Get organization's selected jurisdictions
        from app.models.jurisdiction import OrganizationJurisdiction
        
        result = await db.execute(
            select(ComplianceRequirement, Jurisdiction)
            .join(Jurisdiction)
            .join(OrganizationJurisdiction)
            .where(OrganizationJurisdiction.organization_id == organization_id)
            .where(ComplianceRequirement.is_active == True)
        )
        
        requirements = []
        for req, jurisdiction in result:
            requirements.append({
                'id': req.id,
                'requirement_id': req.requirement_id,
                'title': req.title,
                'description': req.description,
                'category': req.category,
                'criticality': req.criticality,
                'jurisdiction_id': jurisdiction.id,
                'jurisdiction_name': jurisdiction.name,
                'framework': jurisdiction.regulation_type.value
            })
        
        return requirements
    
    def _group_requirements_by_jurisdiction(self, requirements: List[Dict[str, Any]]) -> Dict[UUID, List[Dict[str, Any]]]:
        """Group requirements by jurisdiction for efficient processing"""
        
        groups = {}
        for req in requirements:
            jurisdiction_id = req['jurisdiction_id']
            if jurisdiction_id not in groups:
                groups[jurisdiction_id] = []
            groups[jurisdiction_id].append(req)
        
        return groups
    
    async def _get_jurisdiction(self, jurisdiction_id: UUID, db: AsyncSession) -> Optional[Jurisdiction]:
        """Get jurisdiction by ID"""
        
        result = await db.execute(
            select(Jurisdiction).where(Jurisdiction.id == jurisdiction_id)
        )
        return result.scalar_one_or_none()
    
    async def _fallback_text_analysis(self, company_text: str, requirements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Fallback text analysis when Assistant API is not available"""
        
        assessments = []
        
        for req in requirements:
            # Simple keyword-based analysis
            description = req['description'].lower()
            company_lower = company_text.lower()
            
            # Extract key concepts from requirement
            key_concepts = self._extract_key_concepts(description)
            
            # Check if company document addresses these concepts
            matches = []
            for concept in key_concepts:
                if concept in company_lower:
                    # Find the sentence containing the concept
                    sentences = company_text.split('.')
                    for sentence in sentences:
                        if concept in sentence.lower():
                            matches.append(sentence.strip())
                            break
            
            # Determine status based on matches
            if len(matches) >= len(key_concepts) * 0.7:  # 70% of concepts found
                status = "COMPLIANT"
                evidence = ". ".join(matches[:2])  # First 2 matches as evidence
                gap = ""
                recommendation = "Continue current practices"
            elif len(matches) > 0:
                status = "PARTIAL"
                evidence = ". ".join(matches)
                gap = "Some aspects of the requirement are addressed but implementation may be incomplete"
                recommendation = f"Expand implementation to fully address all aspects of {req['title']}"
            else:
                status = "NOT_ADDRESSED"
                evidence = "No evidence found in the document"
                gap = "This requirement is not addressed in the provided documentation"
                recommendation = f"Implement policies and procedures to address {req['title']}"
            
            assessments.append({
                'requirement_id': req['requirement_id'],
                'status': status,
                'evidence': evidence,
                'gap_description': gap,
                'recommendation': recommendation,
                'confidence': 0.7  # Lower confidence for fallback method
            })
        
        return assessments
    
    def _extract_key_concepts(self, description: str) -> List[str]:
        """Extract key concepts from requirement description"""
        
        # Simple keyword extraction
        key_terms = [
            'human oversight', 'bias testing', 'transparency', 'risk assessment',
            'data governance', 'monitoring', 'documentation', 'training',
            'approval process', 'review', 'audit', 'compliance', 'policy',
            'procedure', 'control', 'measure', 'assessment', 'evaluation'
        ]
        
        concepts = []
        description_lower = description.lower()
        
        for term in key_terms:
            if term in description_lower:
                concepts.append(term)
        
        # If no standard terms found, use the most important words
        if not concepts:
            words = description_lower.split()
            important_words = [w for w in words if len(w) > 4 and w not in ['shall', 'must', 'should', 'will', 'system', 'systems']]
            concepts = important_words[:3]  # Take first 3 important words
        
        return concepts
    
    async def _create_assessment_record(
        self,
        session_id: UUID,
        organization_id: UUID,
        assessment_data: Dict[str, Any],
        requirements: List[Dict[str, Any]],
        db: AsyncSession
    ) -> Optional[ComplianceAssessment]:
        """Create assessment record in database"""
        
        try:
            # Find the requirement this assessment is for
            requirement = None
            for req in requirements:
                if req['requirement_id'] == assessment_data.get('requirement_id'):
                    requirement = req
                    break
            
            if not requirement:
                logger.warning(f"Requirement not found for assessment: {assessment_data.get('requirement_id')}")
                return None
            
            assessment = ComplianceAssessment(
                session_id=session_id,
                organization_id=organization_id,
                requirement_id=requirement['id'],
                status=assessment_data.get('status', 'NOT_ADDRESSED'),
                evidence_text=assessment_data.get('evidence', ''),
                evidence_type='document',
                explanation=assessment_data.get('explanation', ''),
                gap_description=assessment_data.get('gap_description', ''),
                recommendation=assessment_data.get('recommendation', ''),
                confidence_score=assessment_data.get('confidence', 0.0),
                assessed_at=datetime.utcnow()
            )
            
            db.add(assessment)
            return assessment
            
        except Exception as e:
            logger.error(f"Failed to create assessment record: {e}")
            return None
    
    def _calculate_overall_scores(self, assessments: List[ComplianceAssessment]) -> Dict[str, int]:
        """Calculate overall compliance scores"""
        
        total = len(assessments)
        if total == 0:
            return {
                'total': 0, 'compliant': 0, 'partial': 0, 
                'non_compliant': 0, 'not_addressed': 0, 'score': 0
            }
        
        compliant = len([a for a in assessments if a.status == 'COMPLIANT'])
        partial = len([a for a in assessments if a.status == 'PARTIAL'])
        non_compliant = len([a for a in assessments if a.status == 'NON_COMPLIANT'])
        not_addressed = len([a for a in assessments if a.status == 'NOT_ADDRESSED'])
        
        # Calculate weighted score (compliant=100%, partial=50%, others=0%)
        score = int((compliant * 100 + partial * 50) / total) if total > 0 else 0
        
        return {
            'total': total,
            'compliant': compliant,
            'partial': partial,
            'non_compliant': non_compliant,
            'not_addressed': not_addressed,
            'score': score
        }
    
    def _serialize_assessment(self, assessment: ComplianceAssessment) -> Dict[str, Any]:
        """Serialize assessment for API response"""
        
        return {
            'id': str(assessment.id),
            'requirement_id': str(assessment.requirement_id),
            'status': assessment.status,
            'evidence_text': assessment.evidence_text,
            'gap_description': assessment.gap_description,
            'recommendation': assessment.recommendation,
            'confidence_score': assessment.confidence_score,
            'assessed_at': assessment.assessed_at.isoformat() if assessment.assessed_at else None
        }


# Global instance
document_assessor = DocumentAssessor()