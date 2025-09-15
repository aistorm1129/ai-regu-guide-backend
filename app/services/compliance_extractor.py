"""Service for extracting compliance requirements from PDF documents"""

import openai
from typing import Dict, List, Any
from app.config import settings
from app.services.document_processor import document_processor
import json
import logging

logger = logging.getLogger(__name__)


class ComplianceExtractor:
    """Extract structured compliance requirements from PDF documents using AI"""
    
    def __init__(self):
        if settings.OPENAI_API_KEY:
            self.client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        else:
            logger.warning("OpenAI API key not configured - using mock data")
            self.client = None
    
    async def extract_requirements(self, file_path: str, framework: str, use_assistant_api: bool = True, keep_assistant: bool = False) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Extract compliance requirements from a PDF document
        Returns: (requirements, extraction_metadata)

        Args:
            file_path: Path to the PDF document
            framework: Compliance framework (eu_ai_act, us_ai_governance, iso_42001)
            use_assistant_api: Whether to use Assistant API (vs chunking)
            keep_assistant: Whether to keep the assistant persistent (for future comparisons)
        """

        extraction_metadata = {
            "method": None,
            "framework": framework,
            "extracted_text": None,
            "text_length": 0,
            "assistant_id": None,
            "vector_store_id": None,
            "file_id": None
        }

        if not self.client:
            # Return mock requirements if OpenAI not available
            logger.warning("OpenAI client not available, using mock data")
            extraction_metadata["method"] = "mock"
            return self._get_mock_requirements(framework), extraction_metadata

        try:
            if use_assistant_api:
                # Use Assistant API for optimal accuracy
                logger.info(f"🤖 USING OPENAI ASSISTANT API for {framework} extraction")
                extraction_metadata["method"] = "assistant_api"

                from app.services.assistant_manager import assistant_manager

                # Create assistant for this document
                assistant_name = f"{framework}-compliance-assistant" if keep_assistant else f"Temp-{framework}"
                assistant_data = await assistant_manager.create_compliance_assistant(
                    framework, file_path, assistant_name
                )

                # Store assistant data in metadata
                extraction_metadata["assistant_id"] = assistant_data.get("assistant_id")
                extraction_metadata["vector_store_id"] = assistant_data.get("vector_store_id")
                extraction_metadata["file_id"] = assistant_data.get("file_id")

                # Extract requirements using Assistant
                requirements = await assistant_manager.extract_all_requirements(
                    assistant_data["assistant_id"], framework
                )

                if not keep_assistant:
                    # Cleanup temporary assistant
                    logger.info("🗑️ Cleaning up temporary assistant")
                    await assistant_manager.cleanup_assistant(
                        assistant_data["assistant_id"],
                        assistant_data["vector_store_id"],
                        assistant_data["file_id"]
                    )
                    # Clear assistant data from metadata since it's deleted
                    extraction_metadata["assistant_id"] = None
                    extraction_metadata["vector_store_id"] = None
                    extraction_metadata["file_id"] = None
                else:
                    logger.info(f"💾 Keeping persistent assistant: {assistant_data['assistant_id']}")

                if requirements:
                    logger.info(f"✅ Assistant API successfully extracted {len(requirements)} requirements")
                    return requirements, extraction_metadata
                else:
                    logger.warning("⚠️ Assistant API returned no requirements, falling back to chunking")
                    use_assistant_api = False

            if not use_assistant_api:
                # Fallback to chunking method
                logger.info(f"📄 USING CHUNKING METHOD for {framework} extraction")
                extraction_metadata["method"] = "chunking"

                document_text, _ = document_processor.extract_text_from_file(file_path, file_path)
                extraction_metadata["extracted_text"] = document_text
                extraction_metadata["text_length"] = len(document_text)

                logger.info(f"📊 Extracted {len(document_text)} characters from PDF")

                all_requirements = await self._extract_with_chunking(document_text, framework)
                logger.info(f"✅ Chunking method extracted {len(all_requirements)} requirements")

                return all_requirements, extraction_metadata
                
        except Exception as e:
            logger.error(f"Failed to extract requirements: {e}")
            extraction_metadata["method"] = "mock_fallback"
            return self._get_mock_requirements(framework), extraction_metadata
    
    def _build_extraction_prompt(self, document_text: str, framework: str) -> str:
        """Build framework-specific extraction prompt"""
        
        framework_guidance = {
            "eu_ai_act": {
                "pattern": "Article X.Y.Z",
                "categories": ["Prohibited Practices", "High-Risk Systems", "Transparency", "Human Oversight", "Conformity Assessment"]
            },
            "iso_42001": {
                "pattern": "Clause X.Y", 
                "categories": ["Context", "Leadership", "Planning", "Support", "Operation", "Performance Evaluation", "Improvement"]
            },
            "us_ai_governance": {
                "pattern": "Section X.Y",
                "categories": ["Governance", "Risk Management", "Testing", "Monitoring", "Accountability"]
            }
        }
        
        guidance = framework_guidance.get(framework, framework_guidance["eu_ai_act"])
        
        return f"""
Extract structured compliance requirements from this {framework.upper()} regulatory document.

DOCUMENT TEXT (first 8000 chars):
{document_text[:8000]}

Please extract requirements following this JSON structure:
{{
  "requirements": [
    {{
      "requirement_id": "{guidance['pattern']} (e.g., Article 5.1.c)",
      "title": "Brief requirement title",
      "category": "One of: {', '.join(guidance['categories'])}",
      "description": "Complete requirement description",
      "page_number": <page number if found>,
      "section_reference": "Section/Article reference",
      "criticality": "LOW|MEDIUM|HIGH|CRITICAL"
    }}
  ]
}}

EXTRACTION RULES:
1. Extract only explicit regulatory requirements, not explanatory text
2. Use the exact article/section numbers as they appear in the document
3. Categorize each requirement appropriately
4. Set criticality based on:
   - CRITICAL: Prohibited practices, mandatory compliance
   - HIGH: Core requirements with legal consequences
   - MEDIUM: Important procedural requirements
   - LOW: Recommended practices or guidelines
5. Include page numbers when identifiable
6. Focus on actionable compliance requirements

Return only the JSON structure, no additional text.
"""
    
    def _parse_extraction_result(self, result: str, framework: str) -> List[Dict[str, Any]]:
        """Parse AI extraction result into structured format"""
        
        try:
            # Extract JSON from response
            start_idx = result.find('{')
            end_idx = result.rfind('}')
            if start_idx != -1 and end_idx != -1:
                json_str = result[start_idx:end_idx + 1]
                data = json.loads(json_str)
                
                if "requirements" in data:
                    return data["requirements"]
                
        except Exception as e:
            logger.error(f"Failed to parse extraction result: {e}")
        
        # Fallback to mock data
        return self._get_mock_requirements(framework)
    
    def _get_mock_requirements(self, framework: str) -> List[Dict[str, Any]]:
        """Generate mock requirements for testing when OpenAI is unavailable"""
        
        mock_data = {
            "eu_ai_act": [
                {
                    "requirement_id": "Article_5.1.a",
                    "title": "Prohibition of subliminal techniques",
                    "category": "Prohibited Practices",
                    "description": "AI systems that deploy subliminal techniques beyond a person's consciousness to materially distort their behaviour are prohibited.",
                    "page_number": 23,
                    "section_reference": "Article 5(1)(a)",
                    "criticality": "CRITICAL"
                },
                {
                    "requirement_id": "Article_6.1", 
                    "title": "High-risk AI system classification",
                    "category": "High-Risk Systems",
                    "description": "AI systems listed in Annex III shall be considered high-risk AI systems.",
                    "page_number": 25,
                    "section_reference": "Article 6(1)",
                    "criticality": "HIGH"
                }
            ],
            "iso_42001": [
                {
                    "requirement_id": "Clause_4.1",
                    "title": "Understanding the organization and its context",
                    "category": "Context",
                    "description": "The organization shall determine external and internal issues relevant to its purpose and strategic direction.",
                    "page_number": 12,
                    "section_reference": "4.1",
                    "criticality": "HIGH"
                },
                {
                    "requirement_id": "Clause_5.1",
                    "title": "Leadership and commitment",
                    "category": "Leadership", 
                    "description": "Top management shall demonstrate leadership and commitment with respect to the AI management system.",
                    "page_number": 16,
                    "section_reference": "5.1",
                    "criticality": "HIGH"
                }
            ],
            "us_ai_governance": [
                {
                    "requirement_id": "GOVERN-1.1",
                    "title": "AI governance structure",
                    "category": "Governance",
                    "description": "Policies, processes, procedures, and practices across the organization related to the mapping, measuring, and managing of AI risks are in place.",
                    "page_number": 8,
                    "section_reference": "GOVERN-1.1", 
                    "criticality": "HIGH"
                },
                {
                    "requirement_id": "MAP-1.1",
                    "title": "AI system identification",
                    "category": "Risk Management",
                    "description": "Context and business value of AI systems are documented.",
                    "page_number": 12,
                    "section_reference": "MAP-1.1",
                    "criticality": "MEDIUM"
                }
            ]
        }
        
        return mock_data.get(framework, mock_data["eu_ai_act"])
    
    async def _extract_with_chunking(self, document_text: str, framework: str) -> List[Dict[str, Any]]:
        """Extract requirements using intelligent chunking for large documents"""
        
        # Create chunks based on document structure
        chunks = self._create_intelligent_chunks(document_text, framework)
        all_requirements = []
        
        logger.info(f"Processing {len(chunks)} chunks for {framework}")
        
        for i, chunk in enumerate(chunks):
            try:
                # Build framework-specific prompt for this chunk
                prompt = self._build_chunk_extraction_prompt(chunk, framework, i + 1, len(chunks))
                
                response = await self.client.chat.completions.create(
                    model=settings.OPENAI_MODEL,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are an expert compliance analyst specializing in extracting structured requirements from regulatory documents."
                        },
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.1,
                    max_tokens=4000
                )
                
                result = response.choices[0].message.content
                chunk_requirements = self._parse_extraction_result(result, framework)
                
                if chunk_requirements:
                    all_requirements.extend(chunk_requirements)
                    logger.info(f"Extracted {len(chunk_requirements)} requirements from chunk {i + 1}")
                
            except Exception as e:
                logger.error(f"Failed to process chunk {i + 1}: {e}")
                continue
        
        # Deduplicate and merge similar requirements
        final_requirements = self._deduplicate_requirements(all_requirements)
        logger.info(f"Final extraction: {len(final_requirements)} unique requirements")
        
        return final_requirements
    
    def _create_intelligent_chunks(self, document_text: str, framework: str) -> List[str]:
        """Create intelligent chunks based on document structure"""
        
        # Define chunk size (leaving room for prompt overhead)
        max_chunk_chars = 6000
        
        # Framework-specific section markers
        section_patterns = {
            "eu_ai_act": [r"Article \d+", r"Chapter [IVX]+", r"Section \d+"],
            "iso_42001": [r"\d+\.\d+", r"Clause \d+"],
            "us_ai_governance": [r"Section \d+", r"\d+\.\d+", r"GOVERN|MAP|MEASURE|MANAGE"]
        }
        
        patterns = section_patterns.get(framework, [r"Article \d+", r"Section \d+", r"\d+\.\d+"])
        
        # Try to split by sections first
        chunks = self._split_by_sections(document_text, patterns, max_chunk_chars)
        
        # If sections are too large, split by paragraphs
        final_chunks = []
        for chunk in chunks:
            if len(chunk) <= max_chunk_chars:
                final_chunks.append(chunk)
            else:
                # Further split large chunks
                sub_chunks = self._split_by_paragraphs(chunk, max_chunk_chars)
                final_chunks.extend(sub_chunks)
        
        return final_chunks
    
    def _split_by_sections(self, text: str, patterns: List[str], max_chars: int) -> List[str]:
        """Split text by section markers"""
        import re
        
        # Find all section boundaries
        boundaries = []
        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                boundaries.append((match.start(), match.group()))
        
        # Sort boundaries by position
        boundaries.sort(key=lambda x: x[0])
        
        if not boundaries:
            # No sections found, split by character limit
            return [text[i:i + max_chars] for i in range(0, len(text), max_chars)]
        
        chunks = []
        start = 0
        
        for i, (pos, marker) in enumerate(boundaries):
            if i == 0:
                # Content before first section
                if pos > 0:
                    chunk = text[start:pos].strip()
                    if chunk:
                        chunks.append(chunk)
                start = pos
            else:
                # Content of previous section
                chunk = text[start:pos].strip()
                if chunk and len(chunk) > 100:  # Ignore very short sections
                    chunks.append(chunk)
                start = pos
        
        # Last section
        if start < len(text):
            chunk = text[start:].strip()
            if chunk:
                chunks.append(chunk)
        
        return chunks
    
    def _split_by_paragraphs(self, text: str, max_chars: int) -> List[str]:
        """Split text by paragraphs when section-based splitting isn't enough"""
        
        paragraphs = text.split('\n\n')
        chunks = []
        current_chunk = ""
        
        for paragraph in paragraphs:
            if len(current_chunk) + len(paragraph) + 2 <= max_chars:
                current_chunk += paragraph + "\n\n"
            else:
                if current_chunk.strip():
                    chunks.append(current_chunk.strip())
                current_chunk = paragraph + "\n\n"
        
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
        
        return chunks
    
    def _build_chunk_extraction_prompt(self, chunk_text: str, framework: str, chunk_num: int, total_chunks: int) -> str:
        """Build framework-specific extraction prompt for a chunk"""
        
        framework_guidance = {
            "eu_ai_act": {
                "pattern": "Article X.Y.Z",
                "categories": ["Prohibited Practices", "High-Risk Systems", "Transparency", "Human Oversight", "Conformity Assessment"]
            },
            "iso_42001": {
                "pattern": "Clause X.Y", 
                "categories": ["Context", "Leadership", "Planning", "Support", "Operation", "Performance Evaluation", "Improvement"]
            },
            "us_ai_governance": {
                "pattern": "Section X.Y",
                "categories": ["Governance", "Risk Management", "Testing", "Monitoring", "Accountability"]
            }
        }
        
        guidance = framework_guidance.get(framework, framework_guidance["eu_ai_act"])
        
        return f"""
Extract structured compliance requirements from this {framework.upper()} regulatory document chunk {chunk_num} of {total_chunks}.

DOCUMENT TEXT:
{chunk_text}

Please extract requirements following this JSON structure:
{{
  "requirements": [
    {{
      "requirement_id": "{guidance['pattern']} (e.g., Article 5.1.c)",
      "title": "Brief requirement title",
      "category": "One of: {', '.join(guidance['categories'])}",
      "description": "Complete requirement description",
      "page_number": <page number if found>,
      "section_reference": "Section/Article reference",
      "criticality": "LOW|MEDIUM|HIGH|CRITICAL"
    }}
  ]
}}

EXTRACTION RULES:
1. Extract only explicit regulatory requirements, not explanatory text
2. Use the exact article/section numbers as they appear in the document
3. Categorize each requirement appropriately
4. Set criticality based on:
   - CRITICAL: Prohibited practices, mandatory compliance
   - HIGH: Core requirements with legal consequences
   - MEDIUM: Important procedural requirements
   - LOW: Recommended practices or guidelines
5. Include page numbers when identifiable
6. Focus on actionable compliance requirements
7. If this chunk contains no requirements, return {{"requirements": []}}

Return only the JSON structure, no additional text.
"""
    
    def _deduplicate_requirements(self, requirements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove duplicate requirements that may appear across chunks"""
        
        seen_ids = set()
        unique_requirements = []
        
        for req in requirements:
            req_id = req.get("requirement_id", "")
            
            # Skip if we've already seen this requirement ID
            if req_id in seen_ids:
                continue
            
            # Also check for similar titles (handle slight variations)
            title = req.get("title", "").lower()
            is_duplicate = False
            
            for existing in unique_requirements:
                existing_title = existing.get("title", "").lower()
                # Simple similarity check
                if title and existing_title and (
                    title in existing_title or existing_title in title or
                    abs(len(title) - len(existing_title)) < 10
                ):
                    # Keep the one with more detailed description
                    if len(req.get("description", "")) > len(existing.get("description", "")):
                        unique_requirements.remove(existing)
                        break
                    else:
                        is_duplicate = True
                        break
            
            if not is_duplicate:
                unique_requirements.append(req)
                seen_ids.add(req_id)
        
        return unique_requirements


# Global instance
compliance_extractor = ComplianceExtractor()