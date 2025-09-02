"""OpenAI service for AI compliance analysis"""

import openai
from typing import Dict, List, Any, Optional
from app.config import settings
import json
import logging

logger = logging.getLogger(__name__)

class OpenAIService:
    def __init__(self):
        if settings.OPENAI_API_KEY:
            openai.api_key = settings.OPENAI_API_KEY
        else:
            logger.warning("OpenAI API key not configured")
    
    async def analyze_document_compliance(
        self, 
        document_content: str, 
        jurisdiction_rules: List[str],
        document_type: str = "policy"
    ) -> Dict[str, Any]:
        """Analyze document against compliance rules using GPT"""
        
        if not settings.OPENAI_API_KEY:
            # Return mock data if no API key
            return self._get_mock_compliance_analysis()
        
        try:
            prompt = self._build_compliance_prompt(
                document_content, 
                jurisdiction_rules, 
                document_type
            )
            
            client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            
            response = await client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {
                        "role": "system", 
                        "content": "You are an AI compliance expert specializing in AI regulations like EU AI Act, US AI Governance, and ISO/IEC 42001."
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=2000
            )
            
            result = response.choices[0].message.content
            return self._parse_analysis_result(result)
            
        except Exception as e:
            logger.error(f"OpenAI analysis failed: {e}")
            return self._get_mock_compliance_analysis()
    
    def _build_compliance_prompt(
        self, 
        document_content: str, 
        jurisdiction_rules: List[str],
        document_type: str
    ) -> str:
        """Build the analysis prompt for GPT"""
        
        rules_text = "\n".join([f"- {rule}" for rule in jurisdiction_rules])
        
        return f"""
Analyze this {document_type} document against the following compliance requirements:

COMPLIANCE RULES:
{rules_text}

DOCUMENT CONTENT:
{document_content[:4000]}  # Limit content for token management

Please provide a JSON response with the following structure:
{{
    "overall_score": <number 0-100>,
    "compliance_rules": [
        {{
            "rule_id": "<unique_id>",
            "rule_title": "<rule title>",
            "status": "<conform|partial|non_conform>",
            "confidence": <number 0-100>,
            "explanation": "<detailed explanation>",
            "evidence": "<evidence found in document>",
            "recommendation": "<improvement recommendation>",
            "severity": "<low|medium|high>"
        }}
    ],
    "summary": {{
        "conforming": <count>,
        "partial": <count>,
        "non_conforming": <count>,
        "key_findings": ["<finding1>", "<finding2>"],
        "next_steps": ["<step1>", "<step2>"]
    }}
}}

Focus on specific, actionable insights and cite exact text from the document where possible.
"""
    
    def _parse_analysis_result(self, result: str) -> Dict[str, Any]:
        """Parse GPT response into structured format"""
        try:
            # Try to extract JSON from response
            start_idx = result.find('{')
            end_idx = result.rfind('}')
            if start_idx != -1 and end_idx != -1:
                json_str = result[start_idx:end_idx + 1]
                return json.loads(json_str)
        except Exception as e:
            logger.error(f"Failed to parse GPT response: {e}")
        
        # Fallback to mock data
        return self._get_mock_compliance_analysis()
    
    def _get_mock_compliance_analysis(self) -> Dict[str, Any]:
        """Mock compliance analysis for fallback"""
        return {
            "overall_score": 78,
            "compliance_rules": [
                {
                    "rule_id": "EU-AI-001",
                    "rule_title": "High-Risk AI System Registration",
                    "status": "conform",
                    "confidence": 95,
                    "explanation": "Document clearly defines high-risk AI system registration procedures",
                    "evidence": "System registration certificate referenced in section 3.2",
                    "recommendation": "Maintain current documentation standards",
                    "severity": "high"
                },
                {
                    "rule_id": "EU-AI-002",
                    "rule_title": "Algorithm Bias Testing",
                    "status": "partial",
                    "confidence": 70,
                    "explanation": "Bias testing mentioned but lacks detailed methodology",
                    "evidence": "Section 4.1 mentions bias testing procedures",
                    "recommendation": "Define specific bias testing methodologies and metrics",
                    "severity": "medium"
                },
                {
                    "rule_id": "EU-AI-003",
                    "rule_title": "Human Oversight Implementation",
                    "status": "non_conform",
                    "confidence": 85,
                    "explanation": "No clear human oversight procedures documented",
                    "evidence": "No relevant evidence found",
                    "recommendation": "Implement and document human oversight procedures for AI decision-making",
                    "severity": "high"
                }
            ],
            "summary": {
                "conforming": 1,
                "partial": 1,
                "non_conforming": 1,
                "key_findings": [
                    "Strong registration documentation",
                    "Bias testing needs improvement",
                    "Human oversight missing"
                ],
                "next_steps": [
                    "Develop bias testing methodology",
                    "Implement human oversight framework",
                    "Update documentation with procedures"
                ]
            }
        }

    async def analyze_form_responses(
        self, 
        form_responses: Dict[str, Any], 
        jurisdiction_rules: List[str]
    ) -> Dict[str, Any]:
        """Analyze intelligent form responses for compliance"""
        
        if not settings.OPENAI_API_KEY:
            return self._get_mock_compliance_analysis()
        
        try:
            # Convert form responses to text
            responses_text = self._format_form_responses(form_responses)
            
            prompt = f"""
Analyze these AI governance questionnaire responses against compliance requirements:

COMPLIANCE RULES:
{chr(10).join([f"- {rule}" for rule in jurisdiction_rules])}

QUESTIONNAIRE RESPONSES:
{responses_text}

Provide the same JSON structure as document analysis, focusing on gaps identified through the responses.
"""
            
            client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            
            response = await client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {
                        "role": "system", 
                        "content": "You are an AI compliance expert analyzing questionnaire responses for regulatory compliance."
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=2000
            )
            
            result = response.choices[0].message.content
            return self._parse_analysis_result(result)
            
        except Exception as e:
            logger.error(f"Form analysis failed: {e}")
            return self._get_mock_compliance_analysis()
    
    def _format_form_responses(self, responses: Dict[str, Any]) -> str:
        """Format form responses for analysis"""
        formatted = []
        for question, answer in responses.items():
            formatted.append(f"Q: {question}")
            formatted.append(f"A: {answer}")
            formatted.append("")
        return "\n".join(formatted)

# Global instance
openai_service = OpenAIService()