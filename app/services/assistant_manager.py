"""
OpenAI Assistant API manager for compliance document processing
"""

import openai
from typing import Dict, List, Any, Optional
from app.config import settings
import json
import asyncio
import logging

logger = logging.getLogger(__name__)


class AssistantManager:
    """Manage OpenAI Assistants for compliance document processing"""
    
    def __init__(self):
        if settings.OPENAI_API_KEY:
            self.client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        else:
            logger.warning("OpenAI API key not configured")
            self.client = None
    
    async def create_compliance_assistant(self, framework: str, pdf_path: str, jurisdiction_name: str) -> Dict[str, str]:
        """Create an Assistant for a specific compliance framework"""
        
        if not self.client:
            raise Exception("OpenAI client not initialized")
        
        try:
            # Upload PDF file
            with open(pdf_path, "rb") as f:
                file = await self.client.files.create(
                    file=f,
                    purpose='assistants'
                )
            
            # Create vector store
            vector_store = await self.client.beta.vector_stores.create(
                name=f"{jurisdiction_name} Compliance Documents",
                file_ids=[file.id]
            )
            
            # Create assistant with framework-specific instructions
            assistant_instructions = self._get_framework_instructions(framework)
            
            assistant = await self.client.beta.assistants.create(
                name=f"{jurisdiction_name} Compliance Expert",
                instructions=assistant_instructions,
                model=settings.OPENAI_MODEL,
                tools=[{"type": "file_search"}],
                tool_resources={
                    "file_search": {
                        "vector_store_ids": [vector_store.id]
                    }
                }
            )
            
            logger.info(f"Created assistant {assistant.id} for {jurisdiction_name}")
            
            return {
                "assistant_id": assistant.id,
                "vector_store_id": vector_store.id,
                "file_id": file.id
            }
            
        except Exception as e:
            logger.error(f"Failed to create assistant for {jurisdiction_name}: {e}")
            raise
    
    async def extract_all_requirements(self, assistant_id: str, framework: str) -> List[Dict[str, Any]]:
        """Extract all compliance requirements using Assistant API"""
        
        if not self.client:
            return []
        
        try:
            # Create thread for conversation
            thread = await self.client.beta.threads.create()
            
            # Get framework-specific extraction prompt
            extraction_prompt = self._get_extraction_prompt(framework)
            
            # Send extraction request
            await self.client.beta.threads.messages.create(
                thread_id=thread.id,
                role="user",
                content=extraction_prompt
            )
            
            # Run the assistant
            run = await self.client.beta.threads.runs.create(
                thread_id=thread.id,
                assistant_id=assistant_id
            )
            
            # Wait for completion
            while True:
                run_status = await self.client.beta.threads.runs.retrieve(
                    thread_id=thread.id,
                    run_id=run.id
                )
                
                if run_status.status == 'completed':
                    break
                elif run_status.status == 'failed':
                    raise Exception(f"Assistant run failed: {run_status.last_error}")
                
                await asyncio.sleep(2)
            
            # Get the response
            messages = await self.client.beta.threads.messages.list(
                thread_id=thread.id,
                limit=1
            )
            
            response_content = messages.data[0].content[0].text.value
            
            # Parse JSON response
            requirements = self._parse_requirements_response(response_content)
            
            logger.info(f"Extracted {len(requirements)} requirements using Assistant API")
            return requirements
            
        except Exception as e:
            logger.error(f"Failed to extract requirements with Assistant: {e}")
            return []
    
    async def assess_document_against_requirements(
        self, 
        assistant_id: str, 
        company_document_text: str, 
        requirements: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Assess company document against compliance requirements"""
        
        if not self.client:
            return []
        
        try:
            # Create thread
            thread = await self.client.beta.threads.create()
            
            # Build assessment prompt
            assessment_prompt = self._build_assessment_prompt(company_document_text, requirements)
            
            # Send assessment request
            await self.client.beta.threads.messages.create(
                thread_id=thread.id,
                role="user",
                content=assessment_prompt
            )
            
            # Run assessment
            run = await self.client.beta.threads.runs.create(
                thread_id=thread.id,
                assistant_id=assistant_id
            )
            
            # Wait for completion
            while True:
                run_status = await self.client.beta.threads.runs.retrieve(
                    thread_id=thread.id,
                    run_id=run.id
                )
                
                if run_status.status == 'completed':
                    break
                elif run_status.status == 'failed':
                    raise Exception(f"Assessment run failed: {run_status.last_error}")
                
                await asyncio.sleep(2)
            
            # Get assessment results
            messages = await self.client.beta.threads.messages.list(
                thread_id=thread.id,
                limit=1
            )
            
            response_content = messages.data[0].content[0].text.value
            assessments = self._parse_assessment_response(response_content)
            
            logger.info(f"Completed assessment for {len(assessments)} requirements")
            return assessments
            
        except Exception as e:
            logger.error(f"Failed to assess document: {e}")
            return []
    
    def _get_framework_instructions(self, framework: str) -> str:
        """Get framework-specific assistant instructions"""
        
        instructions = {
            "eu_ai_act": """You are an expert on the EU AI Act compliance. You understand all articles, annexes, and implementation requirements. You can extract precise compliance requirements and assess company policies against them. Focus on prohibited practices, high-risk systems, transparency, human oversight, and conformity assessments.""",
            
            "us_ai_governance": """You are an expert on US AI governance including NIST AI Risk Management Framework, Executive Order 14110, and OMB guidance. You understand the GOVERN, MAP, MEASURE, MANAGE functions and can assess organizational AI governance practices against federal requirements.""",
            
            "iso_42001": """You are an expert on ISO/IEC 42001 AI management systems standard. You understand all clauses related to context, leadership, planning, support, operation, performance evaluation, and improvement. You can assess AI management system documentation and practices."""
        }
        
        return instructions.get(framework, instructions["eu_ai_act"])
    
    def _get_extraction_prompt(self, framework: str) -> str:
        """Get framework-specific requirement extraction prompt"""
        
        framework_guidance = {
            "eu_ai_act": {
                "pattern": "Article X.Y.Z",
                "categories": ["Prohibited Practices", "High-Risk Systems", "Transparency", "Human Oversight", "Conformity Assessment", "Data Governance", "Risk Management"]
            },
            "iso_42001": {
                "pattern": "Clause X.Y", 
                "categories": ["Context", "Leadership", "Planning", "Support", "Operation", "Performance Evaluation", "Improvement"]
            },
            "us_ai_governance": {
                "pattern": "Function X.Y",
                "categories": ["GOVERN", "MAP", "MEASURE", "MANAGE"]
            }
        }
        
        guidance = framework_guidance.get(framework, framework_guidance["eu_ai_act"])
        
        return f"""
Please extract ALL compliance requirements from the uploaded regulatory document. 

Return a comprehensive JSON response with this structure:
{{
  "requirements": [
    {{
      "requirement_id": "{guidance['pattern']} (e.g., Article 5.1.c)",
      "title": "Brief requirement title",
      "category": "One of: {', '.join(guidance['categories'])}",
      "description": "Complete requirement description",
      "page_number": <page number if identifiable>,
      "section_reference": "Section/Article reference",
      "criticality": "LOW|MEDIUM|HIGH|CRITICAL",
      "implementation_guidance": "How organizations should implement this",
      "evidence_needed": "What evidence would prove compliance"
    }}
  ]
}}

EXTRACTION REQUIREMENTS:
1. Extract EVERY actionable compliance requirement, not just major ones
2. Include specific obligations, prohibitions, and procedural requirements
3. Use exact article/clause numbers as they appear
4. Set criticality based on legal consequences and enforcement priority
5. Provide implementation guidance in business-friendly language
6. Specify what evidence would demonstrate compliance
7. Ensure comprehensive coverage - don't miss any requirements

Please process the entire document systematically and return complete JSON only.
"""
    
    def _build_assessment_prompt(self, company_document: str, requirements: List[Dict[str, Any]]) -> str:
        """Build prompt for assessing company document against requirements"""
        
        requirements_summary = []
        for i, req in enumerate(requirements[:20]):  # Limit to avoid token overflow
            requirements_summary.append(f"""
Requirement {i+1}:
- ID: {req.get('requirement_id')}
- Title: {req.get('title')}
- Description: {req.get('description')}
- Evidence Needed: {req.get('evidence_needed', 'Documented implementation')}
""")
        
        return f"""
Please assess the following company document against the compliance requirements listed below.

COMPANY DOCUMENT:
{company_document[:8000]}  # Limit document size

REQUIREMENTS TO ASSESS:
{''.join(requirements_summary)}

For EACH requirement, determine:
1. Compliance Status: COMPLIANT, PARTIAL, NON_COMPLIANT, or NOT_ADDRESSED
2. Evidence: Exact quotes from the company document that support the assessment
3. Gap Description: What's missing or insufficient (if not fully compliant)
4. Recommendation: Specific actions to achieve full compliance

Return JSON in this format:
{{
  "assessments": [
    {{
      "requirement_id": "requirement_id",
      "status": "COMPLIANT|PARTIAL|NON_COMPLIANT|NOT_ADDRESSED",
      "evidence": "Exact quote from company document",
      "gap_description": "What's missing or needs improvement",
      "recommendation": "Specific action to take",
      "confidence": 0.95
    }}
  ]
}}

Be thorough and precise. Quote exact text as evidence. Provide actionable recommendations.
"""
    
    def _parse_requirements_response(self, response: str) -> List[Dict[str, Any]]:
        """Parse requirements extraction response"""
        
        try:
            # Find JSON in response
            start_idx = response.find('{')
            end_idx = response.rfind('}') + 1
            
            if start_idx != -1 and end_idx != -1:
                json_str = response[start_idx:end_idx]
                data = json.loads(json_str)
                
                if "requirements" in data:
                    return data["requirements"]
            
        except Exception as e:
            logger.error(f"Failed to parse requirements response: {e}")
        
        return []
    
    def _parse_assessment_response(self, response: str) -> List[Dict[str, Any]]:
        """Parse assessment response"""
        
        try:
            # Find JSON in response
            start_idx = response.find('{')
            end_idx = response.rfind('}') + 1
            
            if start_idx != -1 and end_idx != -1:
                json_str = response[start_idx:end_idx]
                data = json.loads(json_str)
                
                if "assessments" in data:
                    return data["assessments"]
            
        except Exception as e:
            logger.error(f"Failed to parse assessment response: {e}")
        
        return []
    
    async def generate_assessment_questions(
        self,
        assistant_id: str,
        requirements: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Generate intelligent assessment questions for requirements"""
        
        if not self.client:
            return []
        
        try:
            # Create thread
            thread = await self.client.beta.threads.create()
            
            # Build question generation prompt
            question_prompt = self._build_question_generation_prompt(requirements)
            
            # Send request
            await self.client.beta.threads.messages.create(
                thread_id=thread.id,
                role="user",
                content=question_prompt
            )
            
            # Run assistant
            run = await self.client.beta.threads.runs.create(
                thread_id=thread.id,
                assistant_id=assistant_id
            )
            
            # Wait for completion
            while True:
                run_status = await self.client.beta.threads.runs.retrieve(
                    thread_id=thread.id,
                    run_id=run.id
                )
                
                if run_status.status == 'completed':
                    break
                elif run_status.status == 'failed':
                    raise Exception(f"Question generation failed: {run_status.last_error}")
                
                await asyncio.sleep(2)
            
            # Get response
            messages = await self.client.beta.threads.messages.list(
                thread_id=thread.id,
                limit=1
            )
            
            response_content = messages.data[0].content[0].text.value
            questions = self._parse_questions_response(response_content)
            
            logger.info(f"Generated {len(questions)} assessment questions")
            return questions
            
        except Exception as e:
            logger.error(f"Failed to generate questions: {e}")
            return []
    
    def _build_question_generation_prompt(self, requirements: List[Dict[str, Any]]) -> str:
        """Build prompt for generating assessment questions"""
        
        requirements_summary = []
        for i, req in enumerate(requirements):
            requirements_summary.append(f"""
Requirement {i+1}:
- ID: {req.get('requirement_id')}
- Title: {req.get('title')}
- Description: {req.get('description')}
- Criticality: {req.get('criticality')}
""")
        
        return f"""
Generate intelligent assessment questions for the following compliance requirements. Create questions that help determine an organization's compliance status through their responses.

REQUIREMENTS:
{''.join(requirements_summary)}

For each requirement, generate 1-3 targeted questions with these characteristics:
1. Questions should elicit specific, actionable responses
2. Include different question types: multiple choice, text areas, yes/no
3. Questions should help differentiate between COMPLIANT, PARTIAL, NON_COMPLIANT, NOT_ADDRESSED
4. Critical requirements should have more detailed questions
5. Include help text that explains what evidence is expected

Return JSON in this format:
{{
  "questions": [
    {{
      "question_id": "unique_id",
      "requirement_id": "requirement_id",
      "requirement_ref": "Article 5.1.a",
      "question_text": "How does your organization handle...",
      "question_type": "radio|textarea|checkbox|select",
      "required": true|false,
      "options": [
        {{"value": "compliant", "label": "Fully Implemented", "description": "We have comprehensive measures"}},
        {{"value": "partial", "label": "Partially Implemented", "description": "We have some measures but gaps exist"}},
        {{"value": "none", "label": "Not Implemented", "description": "We have no measures in place"}}
      ],
      "help_text": "Explain what evidence or documentation demonstrates compliance",
      "criticality": "HIGH",
      "placeholder": "Describe your current processes..."
    }}
  ]
}}

Generate comprehensive questions that will provide actionable compliance insights.
"""
    
    def _parse_questions_response(self, response: str) -> List[Dict[str, Any]]:
        """Parse question generation response"""
        
        try:
            # Find JSON in response
            start_idx = response.find('{')
            end_idx = response.rfind('}') + 1
            
            if start_idx != -1 and end_idx != -1:
                json_str = response[start_idx:end_idx]
                data = json.loads(json_str)
                
                if "questions" in data:
                    return data["questions"]
            
        except Exception as e:
            logger.error(f"Failed to parse questions response: {e}")
        
        return []
    
    async def cleanup_assistant(self, assistant_id: str, vector_store_id: str = None, file_id: str = None):
        """Clean up assistant resources"""
        
        if not self.client:
            return
        
        try:
            # Delete assistant
            await self.client.beta.assistants.delete(assistant_id)
            
            # Delete vector store if provided
            if vector_store_id:
                await self.client.beta.vector_stores.delete(vector_store_id)
            
            # Delete file if provided
            if file_id:
                await self.client.files.delete(file_id)
                
            logger.info(f"Cleaned up assistant {assistant_id}")
            
        except Exception as e:
            logger.error(f"Failed to cleanup assistant: {e}")


# Global instance
assistant_manager = AssistantManager()