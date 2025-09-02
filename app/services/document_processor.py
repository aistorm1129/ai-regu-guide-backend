"""Document processing service for extracting text from various file formats"""

import os
import tempfile
from pathlib import Path
from typing import Dict, Optional, Tuple
import logging

try:
    import docx
    from PyPDF2 import PdfReader
    import magic
except ImportError as e:
    logging.warning(f"Optional dependencies not available: {e}")

logger = logging.getLogger(__name__)

class DocumentProcessor:
    
    @staticmethod
    def extract_text_from_file(file_path: str, filename: str) -> Tuple[str, str]:
        """
        Extract text from various document formats
        Returns: (extracted_text, file_type)
        """
        try:
            file_ext = Path(filename).suffix.lower()
            
            if file_ext == '.pdf':
                return DocumentProcessor._extract_pdf_text(file_path), 'pdf'
            elif file_ext in ['.docx', '.doc']:
                return DocumentProcessor._extract_docx_text(file_path), 'docx'
            elif file_ext == '.txt':
                return DocumentProcessor._extract_txt_text(file_path), 'txt'
            else:
                # Try to read as plain text
                return DocumentProcessor._extract_txt_text(file_path), 'unknown'
                
        except Exception as e:
            logger.error(f"Failed to extract text from {filename}: {e}")
            return f"Error extracting text from {filename}: {str(e)}", 'error'
    
    @staticmethod
    def _extract_pdf_text(file_path: str) -> str:
        """Extract text from PDF file"""
        try:
            with open(file_path, 'rb') as file:
                pdf_reader = PdfReader(file)
                text = ""
                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n"
                return text.strip()
        except Exception as e:
            logger.error(f"PDF extraction failed: {e}")
            return f"Failed to extract PDF text: {str(e)}"
    
    @staticmethod
    def _extract_docx_text(file_path: str) -> str:
        """Extract text from DOCX file"""
        try:
            doc = docx.Document(file_path)
            text = []
            for paragraph in doc.paragraphs:
                text.append(paragraph.text)
            return '\n'.join(text)
        except Exception as e:
            logger.error(f"DOCX extraction failed: {e}")
            return f"Failed to extract DOCX text: {str(e)}"
    
    @staticmethod
    def _extract_txt_text(file_path: str) -> str:
        """Extract text from plain text file"""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
                return file.read()
        except Exception as e:
            logger.error(f"Text extraction failed: {e}")
            return f"Failed to read text file: {str(e)}"
    
    @staticmethod
    def get_file_info(file_path: str, filename: str) -> Dict[str, str]:
        """Get file information"""
        try:
            stat = os.stat(file_path)
            return {
                'filename': filename,
                'size': str(stat.st_size),
                'extension': Path(filename).suffix.lower(),
                'mime_type': DocumentProcessor._get_mime_type(file_path)
            }
        except Exception as e:
            logger.error(f"Failed to get file info for {filename}: {e}")
            return {
                'filename': filename,
                'size': '0',
                'extension': Path(filename).suffix.lower(),
                'mime_type': 'unknown'
            }
    
    @staticmethod
    def _get_mime_type(file_path: str) -> str:
        """Get MIME type of file"""
        try:
            # Try to use python-magic if available
            return magic.from_file(file_path, mime=True)
        except:
            # Fallback to basic extension mapping
            ext = Path(file_path).suffix.lower()
            mime_types = {
                '.pdf': 'application/pdf',
                '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                '.doc': 'application/msword',
                '.txt': 'text/plain'
            }
            return mime_types.get(ext, 'application/octet-stream')
    
    @staticmethod
    def is_supported_format(filename: str) -> bool:
        """Check if file format is supported"""
        ext = Path(filename).suffix.lower()
        return ext in ['.pdf', '.docx', '.doc', '.txt']
    
    @staticmethod
    def validate_file_size(file_size: int, max_size: int = 10 * 1024 * 1024) -> bool:
        """Validate file size (default 10MB)"""
        return file_size <= max_size

# Global instance
document_processor = DocumentProcessor()