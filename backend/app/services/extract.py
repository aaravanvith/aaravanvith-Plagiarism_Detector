"""File-format-agnostic text extraction for uploaded reports."""
import io
import re

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
    if lower.endswith((".txt", ".md", ".markdown")):
        return content.decode("utf-8", errors="ignore")
    if lower.endswith(".rtf"):
        # Lightweight, dependency-free RTF fallback. Rich formatting is not
        # retained, but the document remains searchable in the repository.
        source = content.decode("utf-8", errors="ignore")
        source = re.sub(r"\\'[0-9a-fA-F]{2}", " ", source)
        source = re.sub(r"\\[a-zA-Z]+-?\d* ?", " ", source)
        return re.sub(r"[{}]", " ", source)
    # fall back: treat as plain text
    return content.decode("utf-8", errors="ignore")
