"""File-format-agnostic text extraction for uploaded reports."""
import io

from pypdf import PdfReader
from docx import Document


def extract_text(filename: str, content: bytes) -> str:
    lower = filename.lower()
    if lower.endswith(".pdf"):
        reader = PdfReader(io.BytesIO(content))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if lower.endswith(".docx"):
        doc = Document(io.BytesIO(content))
        return "\n".join(p.text for p in doc.paragraphs)
    # fall back: treat as plain text
    return content.decode("utf-8", errors="ignore")
