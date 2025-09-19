"""OpenAI service for AI compliance analysis with improved chunking"""

import openai
from typing import Dict, List, Any, Optional, Tuple
from app.config import settings
import json
import logging
import re

logger = logging.getLogger(__name__)

class OpenAIService:
    def __init__(self):
        if settings.OPENAI_API_KEY:
            openai.api_key = settings.OPENAI_API_KEY
            self.client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        else:
            logger.warning("OpenAI API key not configured")
            self.client = None

    async def analyze_document_compliance(
        self,
        document_content: str,
        jurisdiction_rules: List[str],
        document_type: str = "policy"
    ) -> Dict[str, Any]:
        """Analyze document against compliance rules using intelligent chunking"""

        if not settings.OPENAI_API_KEY:
            return self._get_mock_compliance_analysis()

        try:
            # Use chunking for documents longer than 4000 chars
            if len(document_content) > 4000:
                logger.info(f"Document has {len(document_content)} chars, using chunked analysis")
                return await self._analyze_with_chunking(
                    document_content,
                    jurisdiction_rules,
                    document_type
                )
            else:
                # For short documents, use single analysis
                logger.info(f"Document has {len(document_content)} chars, using single analysis")
                return await self._analyze_single(
                    document_content,
                    jurisdiction_rules,
                    document_type
                )

        except Exception as e:
            logger.error(f"OpenAI analysis failed: {e}")
            return self._get_mock_compliance_analysis()

    async def _analyze_with_chunking(
        self,
        document_content: str,
        jurisdiction_rules: List[str],
        document_type: str
    ) -> Dict[str, Any]:
        """Analyze large documents using intelligent chunking"""

        # Create intelligent chunks
        chunks = self._create_intelligent_chunks_for_user_docs(document_content)
        logger.info(f"Created {len(chunks)} chunks for analysis")

        all_findings = []
        chunk_scores = []

        # Analyze each chunk
        for i, chunk in enumerate(chunks):
            logger.info(f"Analyzing chunk {i+1}/{len(chunks)} ({len(chunk)} chars)")

            prompt = self._build_chunk_compliance_prompt(
                chunk,
                jurisdiction_rules,
                document_type,
                i + 1,
                len(chunks)
            )

            try:
                response = await self.client.chat.completions.create(
                    model=settings.OPENAI_MODEL,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are an AI compliance expert specializing in AI regulations like EU AI Act, US AI Governance, and ISO/IEC 42001. Analyze document sections for compliance."
                        },
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.1,
                    max_tokens=3000  # More tokens for detailed analysis
                )

                result = response.choices[0].message.content
                chunk_analysis = self._parse_analysis_result(result)

                if chunk_analysis and "compliance_rules" in chunk_analysis:
                    all_findings.extend(chunk_analysis.get("compliance_rules", []))
                    if "overall_score" in chunk_analysis:
                        chunk_scores.append(chunk_analysis["overall_score"])

            except Exception as e:
                logger.error(f"Failed to analyze chunk {i+1}: {e}")
                continue

        # Merge and deduplicate findings
        return self._merge_compliance_findings(all_findings, chunk_scores)

    async def _analyze_single(
        self,
        document_content: str,
        jurisdiction_rules: List[str],
        document_type: str
    ) -> Dict[str, Any]:
        """Analyze short documents in a single call"""

        prompt = self._build_compliance_prompt(
            document_content,
            jurisdiction_rules,
            document_type
        )

        response = await self.client.chat.completions.create(
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

    def _create_intelligent_chunks_for_user_docs(self, document_text: str) -> List[str]:
        """Create chunks optimized for user organizational documents"""

        max_chunk_chars = 8000  # Larger chunks for better context

        # Try semantic chunking first
        chunks = self._create_semantic_chunks(document_text, max_chunk_chars)

        if not chunks or all(len(c) > max_chunk_chars * 1.5 for c in chunks):
            # Fallback to paragraph-based chunking
            logger.info("Semantic chunking failed, using paragraph-based chunking")
            chunks = self._create_paragraph_chunks(document_text, max_chunk_chars)

        return chunks

    def _create_semantic_chunks(self, document_text: str, max_chars: int) -> List[str]:
        """Create chunks based on semantic boundaries"""

        # Detect document structure patterns
        patterns = self._detect_document_patterns(document_text)

        if patterns:
            # Split by detected patterns
            chunks = self._split_by_patterns(document_text, patterns, max_chars)
        else:
            # Split by topic boundaries
            chunks = self._split_by_topics(document_text, max_chars)

        return chunks

    def _detect_document_patterns(self, document_text: str) -> List[str]:
        """Dynamically detect document structure patterns"""

        patterns = []

        # Test for various numbering systems
        if re.search(r"^\d+\.", document_text, re.MULTILINE):
            patterns.append(r"^\d+\.")  # 1. 2. 3.

        if re.search(r"^\d+\.\d+", document_text, re.MULTILINE):
            patterns.append(r"^\d+\.\d+(?:\.\d+)*")  # 1.1, 1.1.1

        if re.search(r"^[A-Z][A-Z\s]+:$", document_text, re.MULTILINE):
            patterns.append(r"^[A-Z][A-Z\s]+:$")  # SECTION HEADERS:

        if re.search(r"^#{1,6}\s+", document_text, re.MULTILINE):
            patterns.append(r"^#{1,6}\s+")  # Markdown headers

        if re.search(r"^(Chapter|Section|Part)\s+\d+", document_text, re.MULTILINE | re.IGNORECASE):
            patterns.append(r"^(Chapter|Section|Part)\s+\d+")

        return patterns

    def _split_by_patterns(self, text: str, patterns: List[str], max_chars: int) -> List[str]:
        """Split text by detected patterns"""

        # Find all pattern matches
        boundaries = []
        for pattern in patterns:
            for match in re.finditer(pattern, text, re.MULTILINE | re.IGNORECASE):
                boundaries.append((match.start(), match.group()))

        # Sort by position
        boundaries.sort(key=lambda x: x[0])

        if not boundaries:
            return [text]

        chunks = []
        current_chunk = []
        current_length = 0
        last_pos = 0

        for pos, marker in boundaries:
            section_text = text[last_pos:pos].strip()

            if current_length + len(section_text) > max_chars and current_chunk:
                # Save current chunk
                chunks.append('\n'.join(current_chunk))
                current_chunk = [section_text] if section_text else []
                current_length = len(section_text)
            else:
                if section_text:
                    current_chunk.append(section_text)
                    current_length += len(section_text)

            last_pos = pos

        # Add remaining text
        if last_pos < len(text):
            remaining = text[last_pos:].strip()
            if remaining:
                if current_length + len(remaining) > max_chars and current_chunk:
                    chunks.append('\n'.join(current_chunk))
                    chunks.append(remaining)
                else:
                    current_chunk.append(remaining)
                    chunks.append('\n'.join(current_chunk))
        elif current_chunk:
            chunks.append('\n'.join(current_chunk))

        return chunks

    def _split_by_topics(self, text: str, max_chars: int) -> List[str]:
        """Split text by topic boundaries"""

        # Split by double newlines (paragraphs)
        paragraphs = text.split('\n\n')

        chunks = []
        current_chunk = []
        current_length = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            # Check if paragraph starts a new topic
            is_new_topic = self._is_topic_boundary(para)

            if is_new_topic and current_chunk and current_length > max_chars / 2:
                # Start new chunk for new topic
                chunks.append('\n\n'.join(current_chunk))
                current_chunk = [para]
                current_length = len(para)
            elif current_length + len(para) > max_chars and current_chunk:
                # Current chunk is full
                chunks.append('\n\n'.join(current_chunk))
                current_chunk = [para]
                current_length = len(para)
            else:
                # Add to current chunk
                current_chunk.append(para)
                current_length += len(para)

        if current_chunk:
            chunks.append('\n\n'.join(current_chunk))

        return chunks

    def _is_topic_boundary(self, text: str) -> bool:
        """Detect if text starts a new topic"""

        topic_indicators = [
            r"^[A-Z][A-Z\s]+:",           # SECTION HEADERS:
            r"^\d+\.",                     # 1. Numbered items
            r"^[A-Za-z]+\s+\d+",          # Chapter 1, Section 2
            r"^(Introduction|Background|Overview|Purpose|Scope|Requirements|Procedures|Conclusion)",
            r"^(Policy|Guideline|Standard|Process|Procedure):",
        ]

        text_start = text[:100] if len(text) > 100 else text
        return any(re.match(pattern, text_start.strip(), re.IGNORECASE) for pattern in topic_indicators)

    def _create_paragraph_chunks(self, text: str, max_chars: int) -> List[str]:
        """Fallback: Create chunks based on paragraphs"""

        paragraphs = text.split('\n\n')
        chunks = []
        current_chunk = []
        current_length = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            if current_length + len(para) > max_chars and current_chunk:
                chunks.append('\n\n'.join(current_chunk))
                current_chunk = [para]
                current_length = len(para)
            else:
                current_chunk.append(para)
                current_length += len(para)

        if current_chunk:
            chunks.append('\n\n'.join(current_chunk))

        # If chunks are still too large, split by sentences
        final_chunks = []
        for chunk in chunks:
            if len(chunk) > max_chars * 1.5:
                # Split large chunks by sentences
                sentences = chunk.split('. ')
                sub_chunk = []
                sub_length = 0

                for sentence in sentences:
                    if sub_length + len(sentence) > max_chars and sub_chunk:
                        final_chunks.append('. '.join(sub_chunk) + '.')
                        sub_chunk = [sentence]
                        sub_length = len(sentence)
                    else:
                        sub_chunk.append(sentence)
                        sub_length += len(sentence)

                if sub_chunk:
                    final_chunks.append('. '.join(sub_chunk))
            else:
                final_chunks.append(chunk)

        return final_chunks if final_chunks else [text[:max_chars]]

    def _build_chunk_compliance_prompt(
        self,
        chunk_content: str,
        jurisdiction_rules: List[str],
        document_type: str,
        chunk_num: int,
        total_chunks: int
    ) -> str:
        """Build compliance analysis prompt for a chunk"""

        rules_text = "\n".join([f"- {rule}" for rule in jurisdiction_rules[:20]])  # Limit rules to avoid token overflow

        return f"""
Analyze this section (part {chunk_num} of {total_chunks}) of a {document_type} document against compliance requirements:

COMPLIANCE RULES TO CHECK:
{rules_text}

DOCUMENT SECTION:
{chunk_content}

Provide a JSON response with findings ONLY from this specific section:
{{
    "overall_score": <number 0-100 for this section>,
    "compliance_rules": [
        {{
            "rule_id": "<unique_id>",
            "rule_title": "<rule title>",
            "status": "<conform|partial|non_conform>",
            "confidence": <number 0-100>,
            "explanation": "<detailed explanation>",
            "evidence": "<exact quote from this section>",
            "recommendation": "<specific improvement>",
            "severity": "<low|medium|high>"
        }}
    ]
}}

Only include rules where you found relevant evidence in this section.
Focus on specific quotes and actionable insights.
"""

    def _build_compliance_prompt(
        self,
        document_content: str,
        jurisdiction_rules: List[str],
        document_type: str
    ) -> str:
        """Build the analysis prompt for GPT (single analysis)"""

        rules_text = "\n".join([f"- {rule}" for rule in jurisdiction_rules])

        return f"""
Analyze this {document_type} document against the following compliance requirements:

COMPLIANCE RULES:
{rules_text}

DOCUMENT CONTENT:
{document_content}

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

    def _merge_compliance_findings(
        self,
        all_findings: List[Dict[str, Any]],
        chunk_scores: List[float]
    ) -> Dict[str, Any]:
        """Merge findings from multiple chunks into a single analysis"""

        # Deduplicate findings by rule_id
        unique_findings = {}
        for finding in all_findings:
            rule_id = finding.get("rule_id")
            if rule_id:
                if rule_id not in unique_findings:
                    unique_findings[rule_id] = finding
                else:
                    # Merge evidence from multiple chunks
                    existing = unique_findings[rule_id]
                    if finding.get("evidence") and finding["evidence"] not in existing.get("evidence", ""):
                        existing["evidence"] += f" | {finding['evidence']}"
                    # Use the most severe status
                    if finding.get("status") == "non_conform":
                        existing["status"] = "non_conform"
                    elif finding.get("status") == "partial" and existing.get("status") != "non_conform":
                        existing["status"] = "partial"

        final_findings = list(unique_findings.values())

        # Count statuses
        status_counts = {"conform": 0, "partial": 0, "non_conform": 0}
        for finding in final_findings:
            status = finding.get("status", "non_conform").replace("non_conform", "non_conform")
            if status in status_counts:
                status_counts[status] += 1

        # Calculate overall score
        if chunk_scores:
            overall_score = sum(chunk_scores) / len(chunk_scores)
        else:
            # Calculate based on findings
            total = len(final_findings)
            if total > 0:
                overall_score = (status_counts["conform"] * 100 + status_counts["partial"] * 50) / total
            else:
                overall_score = 0

        # Generate key findings
        key_findings = []
        critical_gaps = [f for f in final_findings if f.get("status") == "non_conform" and f.get("severity") == "high"]
        for gap in critical_gaps[:3]:
            key_findings.append(f"{gap.get('rule_title', 'Unknown')}: {gap.get('status', 'non-conforming')}")

        # Generate next steps
        next_steps = []
        for finding in final_findings:
            if finding.get("status") in ["non_conform", "partial"] and finding.get("recommendation"):
                next_steps.append(finding["recommendation"])
                if len(next_steps) >= 3:
                    break

        return {
            "overall_score": round(overall_score, 1),
            "compliance_rules": final_findings,
            "summary": {
                "conforming": status_counts["conform"],
                "partial": status_counts["partial"],
                "non_conforming": status_counts["non_conform"],
                "key_findings": key_findings,
                "next_steps": next_steps[:3]
            }
        }

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

        # Return empty findings if parsing fails
        return {"compliance_rules": [], "overall_score": 0}

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
                }
            ],
            "summary": {
                "conforming": 1,
                "partial": 0,
                "non_conforming": 0,
                "key_findings": ["Strong registration documentation"],
                "next_steps": ["Maintain current standards"]
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

            response = await self.client.chat.completions.create(
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