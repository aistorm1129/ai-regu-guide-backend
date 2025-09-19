from typing import Dict, List, Any, Optional
import json
import logging
from datetime import datetime
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select

from app.models.compliance import ComplianceRequirement, AssessmentSession, ComplianceAssessment
from app.models.jurisdiction import Jurisdiction, OrganizationJurisdiction
from app.models.user import User
from app.models.document import Document, DocumentAnalysis, AnalysisStatus
from app.config import settings

logger = logging.getLogger(__name__)


class FormGenerator:
    """Service for generating dynamic compliance questionnaires and processing form submissions"""
    
    def __init__(self):
        self.openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY) if settings.OPENAI_API_KEY else None
        
    async def generate_questionnaire(
        self,
        db: AsyncSession,
        jurisdiction_id: int,
        use_assistant_api: bool = True
    ) -> Dict[str, Any]:
        """Generate a dynamic questionnaire based on jurisdiction requirements and uploaded compliance data"""
        try:
            # Get jurisdiction with compliance requirements
            result = await db.execute(
                select(Jurisdiction)
                .options(selectinload(Jurisdiction.requirements))
                .where(Jurisdiction.id == jurisdiction_id)
            )
            jurisdiction = result.scalar_one_or_none()

            if not jurisdiction:
                raise ValueError(f"Jurisdiction {jurisdiction_id} not found")

            compliance_requirements = jurisdiction.requirements

            # Use ComplianceRequirement table for fast, cost-effective questionnaire generation
            # This table contains requirements extracted from admin documents
            logger.info(f"Generating questionnaire from ComplianceRequirement table for jurisdiction {jurisdiction.name}")
            return await self._generate_from_requirements(jurisdiction, compliance_requirements)
                
        except Exception as e:
            logger.error(f"Error generating questionnaire: {str(e)}")
            raise

    async def _generate_from_requirements(
        self,
        jurisdiction: Jurisdiction,
        compliance_requirements: List[ComplianceRequirement]
    ) -> Dict[str, Any]:
        """Generate questionnaire directly from ComplianceRequirement table (fast & cost-effective)"""
        try:
            if not compliance_requirements:
                # Fallback to basic template if no requirements in database
                return await self._generate_basic_template(jurisdiction)

            # Group requirements by category
            categories = {}
            for requirement in compliance_requirements:
                category = requirement.category or "General Compliance"
                if category not in categories:
                    categories[category] = []
                categories[category].append(requirement)

            # Generate questions from requirements
            questionnaire_categories = []
            for category_name, requirements in categories.items():
                questions = []

                for requirement in requirements[:15]:  # Limit to prevent overly long forms
                    questions.append({
                        "id": f"req_{requirement.requirement_id}",
                        "question": f"How does your organization address: {requirement.title}?",
                        "description": requirement.description,
                        "type": "textarea",
                        "required": requirement.criticality in ["high", "critical"],
                        "category": category_name,
                        "requirement_id": requirement.requirement_id,
                        "criticality": requirement.criticality
                    })

                    # Add specific follow-up questions based on requirement type
                    if requirement.criticality in ["high", "critical"]:
                        questions.append({
                            "id": f"req_{requirement.requirement_id}_evidence",
                            "question": f"What documentation/evidence supports your compliance with: {requirement.title}?",
                            "type": "textarea",
                            "required": False,
                            "category": category_name,
                            "parent_requirement": requirement.requirement_id
                        })

                questionnaire_categories.append({
                    "category": category_name,
                    "description": f"Questions related to {category_name.lower()} compliance requirements",
                    "questions": questions
                })

            return {
                "title": f"{jurisdiction.name} Compliance Assessment",
                "description": f"Dynamic questionnaire based on {jurisdiction.name} requirements",
                "categories": questionnaire_categories,
                "metadata": {
                    "jurisdiction_id": str(jurisdiction.id),
                    "total_requirements": len(compliance_requirements),
                    "generation_method": "requirements_table",
                    "generated_at": datetime.utcnow().isoformat()
                }
            }

        except Exception as e:
            logger.error(f"Error generating questionnaire from requirements: {str(e)}")
            # Fallback to basic template
            return await self._generate_basic_template(jurisdiction)

    async def _generate_basic_template(self, jurisdiction: Jurisdiction) -> Dict[str, Any]:
        """Basic fallback questionnaire template"""
        return {
            "title": f"{jurisdiction.name} Basic Assessment",
            "description": "Basic compliance assessment questionnaire",
            "categories": [
                {
                    "category": "General Compliance",
                    "description": "General compliance questions",
                    "questions": [
                        {
                            "id": "basic_1",
                            "question": "Does your organization have documented AI governance policies?",
                            "type": "radio",
                            "options": ["Yes", "No", "In Development"],
                            "required": True
                        },
                        {
                            "id": "basic_2",
                            "question": "How do you currently assess AI system risks?",
                            "type": "textarea",
                            "required": True
                        }
                    ]
                }
            ],
            "metadata": {
                "jurisdiction_id": str(jurisdiction.id),
                "generation_method": "basic_template",
                "generated_at": datetime.utcnow().isoformat()
            }
        }

    async def _get_uploaded_compliance_data(self, db: AsyncSession, jurisdiction_id: int) -> Dict[str, Any]:
        """Get compliance data from uploaded documents that have been analyzed"""
        try:
            # Get all organizations that have this jurisdiction
            org_result = await db.execute(
                select(OrganizationJurisdiction.organization_id)
                .where(OrganizationJurisdiction.jurisdiction_id == jurisdiction_id)
            )
            organization_ids = [row[0] for row in org_result.fetchall()]

            if not organization_ids:
                return {}

            # Get documents from these organizations that have completed analysis
            doc_result = await db.execute(
                select(Document, DocumentAnalysis)
                .join(DocumentAnalysis)
                .where(
                    Document.organization_id.in_(organization_ids),
                    DocumentAnalysis.status == AnalysisStatus.COMPLETED,
                    DocumentAnalysis.result.is_not(None)
                )
            )

            compliance_data = {
                "documents": [],
                "extracted_requirements": [],
                "compliance_patterns": []
            }

            for document, analysis in doc_result:
                if analysis.result:
                    doc_data = {
                        "filename": document.filename,
                        "document_type": document.document_type.value,
                        "analysis": analysis.result
                    }
                    compliance_data["documents"].append(doc_data)

                    # Extract any compliance rules or requirements from the analysis
                    if "compliance_rules" in analysis.result:
                        for rule in analysis.result["compliance_rules"]:
                            compliance_data["extracted_requirements"].append({
                                "title": rule.get("rule_title"),
                                "description": rule.get("explanation"),
                                "status": rule.get("status"),
                                "category": rule.get("category", "General"),
                                "source_document": document.filename
                            })

            return compliance_data

        except Exception as e:
            logger.error(f"Error getting uploaded compliance data: {str(e)}")
            return {}

    async def _generate_with_assistant_api(
        self,
        jurisdiction: Jurisdiction,
        compliance_requirements: List[ComplianceRequirement]
    ) -> Dict[str, Any]:
        """Generate questionnaire using OpenAI Assistant API"""
        try:
            # Prepare context about existing requirements
            requirements_context = []
            for requirement in compliance_requirements[:20]:  # Limit for token efficiency
                requirements_context.append({
                    "requirement_id": requirement.requirement_id,
                    "title": requirement.title,
                    "description": requirement.description,
                    "category": requirement.category,
                    "criticality": requirement.criticality
                })
            
            # Create a thread with the assistant
            thread = await self.openai_client.beta.threads.create()
            
            # Prepare the message for questionnaire generation
            json_example = """
{
  "questionnaire": {
    "title": "Compliance Assessment Questionnaire",
    "description": "Brief description",
    "categories": [
      {
        "category": "Category Name",
        "description": "Category description",
        "questions": [
          {
            "id": "q1",
            "question": "Question text",
            "type": "multiple_choice|yes_no|scale|text",
            "options": ["Option 1", "Option 2"] (if applicable),
            "requirement_id": "associated requirement id",
            "risk_weight": "high|medium|low",
            "help_text": "Optional guidance"
          }
        ]
      }
    ]
  }
}
"""
            
            message_content = f"""
Based on the {jurisdiction.name} compliance framework, generate a comprehensive questionnaire to assess organizational compliance. 

Existing compliance requirements context:
{json.dumps(requirements_context, indent=2)}

Please generate a structured questionnaire with the following specifications:

1. **Question Categories**: Organize questions into logical categories (e.g., "Data Governance", "Risk Management", "Human Oversight", "Transparency")

2. **Question Types**: Use varied question types:
   - Multiple choice (with 3-4 options)
   - Yes/No questions
   - Scale ratings (1-5)
   - Short text responses

3. **Question Structure**: Each question should have:
   - Clear, concise question text
   - Question type
   - Answer options (if applicable)
   - Associated requirement_id (if applicable)
   - Risk weight (high/medium/low)

4. **Coverage**: Ensure questions cover key compliance areas:
   - Risk assessment and categorization
   - Data protection and privacy
   - Algorithm transparency and explainability
   - Human oversight and control
   - Documentation and record-keeping
   - Monitoring and auditing

5. **Output Format**: Return as JSON with this structure:
```json{json_example}```

Generate 15-25 questions total, distributed across 4-6 categories. Focus on practical, actionable questions that can effectively assess compliance readiness.
"""
            
            # Add message to thread
            await self.openai_client.beta.threads.messages.create(
                thread_id=thread.id,
                role="user",
                content=message_content
            )
            
            # Run the assistant
            run = await self.openai_client.beta.threads.runs.create(
                thread_id=thread.id,
                assistant_id=jurisdiction.assistant_id
            )
            
            # Wait for completion (with timeout)
            import asyncio
            timeout = 60  # 60 seconds timeout
            start_time = datetime.now()
            
            while run.status in ['queued', 'in_progress']:
                if (datetime.now() - start_time).seconds > timeout:
                    raise TimeoutError("Assistant API timeout")
                await asyncio.sleep(2)
                run = await self.openai_client.beta.threads.runs.retrieve(
                    thread_id=thread.id,
                    run_id=run.id
                )
            
            if run.status != 'completed':
                raise Exception(f"Assistant run failed with status: {run.status}")
            
            # Get the assistant's response
            messages = await self.openai_client.beta.threads.messages.list(
                thread_id=thread.id,
                order="desc",
                limit=1
            )
            
            assistant_response = messages.data[0].content[0].text.value
            
            # Parse the JSON response
            try:
                # Extract JSON from the response (in case there's extra text)
                import re
                json_match = re.search(r'```json\s*(.*?)\s*```', assistant_response, re.DOTALL)
                if json_match:
                    json_text = json_match.group(1)
                else:
                    # Try to find JSON without code blocks
                    json_start = assistant_response.find('{')
                    json_end = assistant_response.rfind('}') + 1
                    if json_start >= 0 and json_end > json_start:
                        json_text = assistant_response[json_start:json_end]
                    else:
                        json_text = assistant_response
                
                questionnaire_data = json.loads(json_text)
                return questionnaire_data
                
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse assistant JSON response: {e}")
                # Fall back to template generation
                return await self._generate_with_templates(jurisdiction, compliance_requirements)
                
        except Exception as e:
            logger.error(f"Error with Assistant API questionnaire generation: {str(e)}")
            # Fall back to template generation
            return await self._generate_with_templates(jurisdiction, compliance_requirements)
    
    async def _generate_with_templates(
        self,
        jurisdiction: Jurisdiction,
        compliance_requirements: List[ComplianceRequirement],
        uploaded_compliance_data: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Generate questionnaire using predefined templates"""
        
        # Template questions based on common compliance frameworks
        if "EU AI Act" in jurisdiction.name:
            return self._get_eu_ai_act_questionnaire(compliance_requirements)
        elif "US AI Governance" in jurisdiction.name:
            return self._get_us_ai_governance_questionnaire(compliance_requirements)
        elif "ISO" in jurisdiction.name:
            return self._get_iso_42001_questionnaire(compliance_requirements)
        else:
            return self._get_generic_questionnaire(compliance_requirements)
    
    def _get_eu_ai_act_questionnaire(self, compliance_requirements: List[ComplianceRequirement]) -> Dict[str, Any]:
        """EU AI Act specific questionnaire template"""
        return {
            "questionnaire": {
                "title": "EU AI Act Compliance Assessment",
                "description": "Assess your organization's readiness for EU AI Act compliance",
                "categories": [
                    {
                        "category": "AI System Classification",
                        "description": "Determine the risk category of your AI systems",
                        "questions": [
                            {
                                "id": "q1",
                                "question": "Does your AI system fall into any prohibited AI practices (e.g., social scoring, real-time biometric identification)?",
                                "type": "yes_no",
                                "requirement_id": self._find_requirement_id(compliance_requirements, "prohibited"),
                                "risk_weight": "high",
                                "help_text": "Prohibited AI practices are banned under the EU AI Act"
                            },
                            {
                                "id": "q2", 
                                "question": "What is the primary risk level of your AI system?",
                                "type": "multiple_choice",
                                "options": ["Minimal Risk", "Limited Risk", "High Risk", "Unacceptable Risk"],
                                "requirement_id": self._find_requirement_id(compliance_requirements, "risk"),
                                "risk_weight": "high"
                            },
                            {
                                "id": "q3",
                                "question": "Is your AI system used in critical infrastructure, education, employment, or law enforcement?",
                                "type": "yes_no", 
                                "requirement_id": self._find_requirement_id(compliance_requirements, "high-risk"),
                                "risk_weight": "high"
                            }
                        ]
                    },
                    {
                        "category": "Risk Management",
                        "description": "Risk management system requirements",
                        "questions": [
                            {
                                "id": "q4",
                                "question": "Do you have a documented risk management system for your AI systems?",
                                "type": "yes_no",
                                "requirement_id": self._find_requirement_id(compliance_requirements, "risk management"),
                                "risk_weight": "high"
                            },
                            {
                                "id": "q5",
                                "question": "How regularly do you conduct risk assessments of your AI systems?",
                                "type": "multiple_choice",
                                "options": ["Never", "Annually", "Quarterly", "Continuously"],
                                "requirement_id": self._find_requirement_id(compliance_requirements, "assessment"),
                                "risk_weight": "medium"
                            }
                        ]
                    },
                    {
                        "category": "Data Governance",
                        "description": "Data quality and governance requirements", 
                        "questions": [
                            {
                                "id": "q6",
                                "question": "Do you have documented data governance procedures for training data?",
                                "type": "yes_no",
                                "requirement_id": self._find_requirement_id(compliance_requirements, "data"),
                                "risk_weight": "medium"
                            },
                            {
                                "id": "q7",
                                "question": "Rate your data quality assurance processes (1=None, 5=Comprehensive)",
                                "type": "scale",
                                "options": ["1", "2", "3", "4", "5"],
                                "requirement_id": self._find_requirement_id(compliance_requirements, "quality"),
                                "risk_weight": "medium"
                            }
                        ]
                    },
                    {
                        "category": "Transparency",
                        "description": "Transparency and explainability requirements",
                        "questions": [
                            {
                                "id": "q8",
                                "question": "Can users easily identify when they are interacting with an AI system?",
                                "type": "yes_no",
                                "requirement_id": self._find_requirement_id(compliance_requirements, "transparency"),
                                "risk_weight": "medium"
                            },
                            {
                                "id": "q9",
                                "question": "Do you provide clear information about your AI system's capabilities and limitations?",
                                "type": "yes_no",
                                "requirement_id": self._find_requirement_id(compliance_requirements, "information"),
                                "risk_weight": "medium"
                            }
                        ]
                    },
                    {
                        "category": "Human Oversight",
                        "description": "Human oversight and control mechanisms",
                        "questions": [
                            {
                                "id": "q10",
                                "question": "Is there meaningful human oversight of high-risk AI system decisions?",
                                "type": "yes_no",
                                "requirement_id": self._find_requirement_id(compliance_requirements, "oversight"),
                                "risk_weight": "high"
                            },
                            {
                                "id": "q11",
                                "question": "Can human operators override AI system decisions when necessary?",
                                "type": "yes_no",
                                "requirement_id": self._find_requirement_id(compliance_requirements, "control"),
                                "risk_weight": "high"
                            }
                        ]
                    }
                ]
            }
        }
    
    def _get_us_ai_governance_questionnaire(self, compliance_requirements: List[ComplianceRequirement]) -> Dict[str, Any]:
        """US AI Governance questionnaire template"""
        return {
            "questionnaire": {
                "title": "US AI Governance Compliance Assessment",
                "description": "Assess compliance with US AI governance frameworks and NIST AI RMF",
                "categories": [
                    {
                        "category": "AI Risk Management Framework",
                        "description": "NIST AI RMF implementation",
                        "questions": [
                            {
                                "id": "q1",
                                "question": "Have you implemented a formal AI Risk Management Framework?",
                                "type": "yes_no",
                                "requirement_id": self._find_requirement_id(compliance_requirements, "framework"),
                                "risk_weight": "high"
                            },
                            {
                                "id": "q2",
                                "question": "Which NIST AI RMF functions have you implemented?",
                                "type": "multiple_choice",
                                "options": ["None", "Govern only", "Map & Measure", "Manage", "All functions"],
                                "requirement_id": self._find_requirement_id(compliance_requirements, "NIST"),
                                "risk_weight": "high"
                            }
                        ]
                    },
                    {
                        "category": "Algorithmic Accountability",
                        "description": "Accountability and transparency in algorithmic decision-making",
                        "questions": [
                            {
                                "id": "q3",
                                "question": "Do you maintain algorithmic impact assessments for high-stakes decisions?",
                                "type": "yes_no",
                                "requirement_id": self._find_requirement_id(compliance_requirements, "algorithmic"),
                                "risk_weight": "high"
                            }
                        ]
                    }
                ]
            }
        }
    
    def _get_iso_42001_questionnaire(self, compliance_requirements: List[ComplianceRequirement]) -> Dict[str, Any]:
        """ISO 42001 questionnaire template"""
        return {
            "questionnaire": {
                "title": "ISO/IEC 42001 AI Management System Assessment", 
                "description": "Assess your AI Management System against ISO/IEC 42001 requirements",
                "categories": [
                    {
                        "category": "AI Management System",
                        "description": "Core AI management system requirements",
                        "questions": [
                            {
                                "id": "q1",
                                "question": "Have you established an AI management system with defined scope and objectives?",
                                "type": "yes_no",
                                "requirement_id": self._find_requirement_id(compliance_requirements, "management"),
                                "risk_weight": "high"
                            }
                        ]
                    }
                ]
            }
        }
    
    def _get_generic_questionnaire(self, compliance_requirements: List[ComplianceRequirement]) -> Dict[str, Any]:
        """Generic compliance questionnaire"""
        return {
            "questionnaire": {
                "title": "AI Compliance Assessment",
                "description": "General AI compliance assessment questionnaire",
                "categories": [
                    {
                        "category": "General Compliance",
                        "description": "Basic AI compliance questions",
                        "questions": [
                            {
                                "id": "q1",
                                "question": "Do you have documented AI governance policies?",
                                "type": "yes_no",
                                "requirement_id": None,
                                "risk_weight": "medium"
                            }
                        ]
                    }
                ]
            }
        }
    
    def _find_requirement_id(self, compliance_requirements: List[ComplianceRequirement], keyword: str) -> Optional[str]:
        """Find a compliance requirement ID that contains the keyword"""
        for requirement in compliance_requirements:
            if keyword.lower() in requirement.title.lower() or keyword.lower() in requirement.description.lower():
                return requirement.requirement_id
        return None
    
    async def process_questionnaire_submission(
        self,
        db: AsyncSession,
        user_id: int,
        jurisdiction_id: int,
        responses: Dict[str, Any],
        questionnaire_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Process questionnaire responses and create assessment session"""
        try:
            # Create assessment session
            session = AssessmentSession(
                user_id=user_id,
                jurisdiction_id=jurisdiction_id,
                session_type='questionnaire',
                source_document_name=None,
                created_at=datetime.utcnow()
            )
            db.add(session)
            await db.flush()  # Get the session ID
            
            # Process each response and create assessments
            total_questions = 0
            compliant_count = 0
            partial_count = 0
            non_compliant_count = 0
            not_addressed_count = 0
            
            assessments = []
            
            for category in questionnaire_data["questionnaire"]["categories"]:
                for question in category["questions"]:
                    question_id = question["id"]
                    user_response = responses.get(question_id, "")
                    
                    if not user_response:
                        not_addressed_count += 1
                        compliance_status = "not_addressed"
                        score = 0
                    else:
                        # Score based on response type and content
                        compliance_status, score = self._score_response(question, user_response)
                        
                        if compliance_status == "compliant":
                            compliant_count += 1
                        elif compliance_status == "partial":
                            partial_count += 1
                        elif compliance_status == "non_compliant":
                            non_compliant_count += 1
                    
                    # Create compliance assessment record
                    assessment = ComplianceAssessment(
                        session_id=session.id,
                        requirement_id=question.get("requirement_id", f"q_{question_id}"),
                        requirement_text=question["question"],
                        compliance_status=compliance_status,
                        score=score,
                        evidence=user_response,
                        recommendations=self._generate_recommendation(question, compliance_status),
                        assessed_at=datetime.utcnow()
                    )
                    assessments.append(assessment)
                    total_questions += 1
            
            # Add all assessments
            for assessment in assessments:
                db.add(assessment)
            
            # Calculate overall score
            if total_questions > 0:
                overall_score = round(
                    (compliant_count * 100 + partial_count * 50) / total_questions
                )
            else:
                overall_score = 0
            
            # Update session with results
            session.overall_score = overall_score
            session.total_requirements = total_questions
            session.compliant_count = compliant_count
            session.partial_count = partial_count
            session.non_compliant_count = non_compliant_count
            session.not_addressed_count = not_addressed_count
            session.completed_at = datetime.utcnow()
            
            await db.commit()
            
            return {
                "session_id": session.id,
                "overall_score": overall_score,
                "total_requirements": total_questions,
                "compliant": compliant_count,
                "partial": partial_count,
                "non_compliant": non_compliant_count,
                "not_addressed": not_addressed_count,
                "assessments": [
                    {
                        "requirement_id": a.requirement_id,
                        "requirement_text": a.requirement_text,
                        "compliance_status": a.compliance_status,
                        "score": a.score,
                        "evidence": a.evidence,
                        "recommendations": a.recommendations
                    }
                    for a in assessments
                ]
            }
            
        except Exception as e:
            await db.rollback()
            logger.error(f"Error processing questionnaire submission: {str(e)}")
            raise
    
    def _score_response(self, question: Dict[str, Any], response: str) -> tuple[str, int]:
        """Score a questionnaire response"""
        question_type = question["type"]
        risk_weight = question.get("risk_weight", "medium")
        
        if question_type == "yes_no":
            if response.lower() in ["yes", "true", "1"]:
                return "compliant", 100
            else:
                # For high-risk questions, "no" is more critical
                if risk_weight == "high":
                    return "non_compliant", 0
                else:
                    return "partial", 25
                    
        elif question_type == "multiple_choice":
            # Score based on the selected option (heuristic approach)
            options = question.get("options", [])
            if response in options:
                option_index = options.index(response)
                # Assume later options are generally better compliance
                score = min(100, (option_index + 1) * (100 // len(options)))
                
                if score >= 75:
                    return "compliant", score
                elif score >= 40:
                    return "partial", score
                else:
                    return "non_compliant", score
            else:
                return "not_addressed", 0
                
        elif question_type == "scale":
            try:
                scale_value = int(response)
                score = scale_value * 20  # Convert 1-5 scale to 0-100
                
                if score >= 80:
                    return "compliant", score
                elif score >= 40:
                    return "partial", score
                else:
                    return "non_compliant", score
            except ValueError:
                return "not_addressed", 0
                
        elif question_type == "text":
            # For text responses, check length and keywords as basic scoring
            if len(response.strip()) > 10:  # Has substantial content
                # Look for positive compliance keywords
                positive_keywords = ["yes", "implement", "establish", "document", "policy", "procedure", "regular"]
                negative_keywords = ["no", "not", "never", "none", "lack"]
                
                response_lower = response.lower()
                positive_count = sum(1 for word in positive_keywords if word in response_lower)
                negative_count = sum(1 for word in negative_keywords if word in response_lower)
                
                if positive_count > negative_count:
                    return "partial", 60
                else:
                    return "non_compliant", 20
            else:
                return "not_addressed", 0
        
        return "not_addressed", 0
    
    def _generate_recommendation(self, question: Dict[str, Any], compliance_status: str) -> str:
        """Generate basic recommendations based on question and compliance status"""
        if compliance_status == "compliant":
            return "Continue maintaining current practices. Consider regular reviews to ensure ongoing compliance."
        
        risk_weight = question.get("risk_weight", "medium")
        question_text = question["question"]
        
        recommendations = {
            "high": {
                "non_compliant": "URGENT: This is a high-risk compliance gap. Immediate action required to establish proper controls and documentation.",
                "partial": "HIGH PRIORITY: Enhance existing measures to fully meet requirements. Consider additional resources and expert consultation.",
                "not_addressed": "CRITICAL: This high-risk area requires immediate attention. Develop and implement comprehensive policies and procedures."
            },
            "medium": {
                "non_compliant": "Develop and implement appropriate policies and procedures to address this requirement.",
                "partial": "Improve existing processes to fully meet compliance requirements. Regular monitoring recommended.",
                "not_addressed": "Establish proper controls and documentation for this compliance area."
            },
            "low": {
                "non_compliant": "Consider implementing basic controls to address this requirement when resources permit.",
                "partial": "Minor improvements needed to achieve full compliance.",
                "not_addressed": "Review and address this requirement as part of your compliance improvement plan."
            }
        }
        
        return recommendations.get(risk_weight, {}).get(compliance_status, 
            "Review this area and implement appropriate measures to improve compliance.")


# Global form generator instance
form_generator = FormGenerator()