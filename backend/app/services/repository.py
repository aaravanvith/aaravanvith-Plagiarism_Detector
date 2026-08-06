"""Local academic-repository ingestion helpers.

This module deliberately stores portable text and metadata in SQLite. It does
not depend on a cloud database, vector service, or external API.
"""
from __future__ import annotations

import hashlib
import re
import uuid

from sqlalchemy.orm import Session

from ..database import AcademicDocument, DocumentParagraph
from .preprocessing import content_words, tokenize


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def extract_keywords(text: str, limit: int = 12) -> list[str]:
    counts: dict[str, int] = {}
    for word in content_words(text):
        counts[word] = counts.get(word, 0) + 1
    return [word for word, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]]


def split_paragraphs(raw_text: str, fallback_text: str) -> list[str]:
    paragraphs = [re.sub(r"\s+", " ", part).strip() for part in re.split(r"\n\s*\n+", raw_text)]
    paragraphs = [part for part in paragraphs if len(tokenize(part)) >= 4]
    return paragraphs or [fallback_text]


def add_document(
    db: Session,
    *,
    filename: str,
    raw_text: str,
    text: str,
    metadata: dict[str, str | None],
    source_report_id: int | None = None,
    ai_score: float | None = None,
    similarity_score: float | None = None,
) -> AcademicDocument:
    """Persist a document and paragraph records without altering legacy reports."""
    digest = content_hash(text)
    existing = db.query(AcademicDocument).filter(AcademicDocument.content_hash == digest).first()
    if existing:
        return existing

    title = metadata.get("title") or filename.rsplit(".", 1)[0]
    keywords = extract_keywords(text)
    document = AcademicDocument(
        document_id=str(uuid.uuid4()),
        source_report_id=source_report_id,
        filename=filename,
        title=title,
        student_name=metadata.get("student_name"),
        usn=metadata.get("usn"),
        department=metadata.get("department"),
        branch=metadata.get("branch"),
        semester=metadata.get("semester"),
        subject=metadata.get("subject"),
        guide=metadata.get("guide"),
        college=metadata.get("college"),
        academic_year=metadata.get("academic_year"),
        project_type=metadata.get("project_type"),
        language=metadata.get("language") or "en",
        text=text,
        abstract=" ".join(text.split()[:80]),
        keywords=", ".join(keywords),
        content_hash=digest,
        word_count=len(tokenize(text)),
        page_count=max(1, raw_text.count("\f") + 1),
        reference_count=len(re.findall(r"\b(references|bibliography)\b", raw_text, re.IGNORECASE)),
        ai_score=ai_score,
        similarity_score=similarity_score,
        approval_status="approved",
    )
    db.add(document)
    db.flush()

    for position, paragraph_text in enumerate(split_paragraphs(raw_text, text), start=1):
        paragraph_hash = content_hash(paragraph_text)
        db.add(DocumentParagraph(
            document_id=document.id,
            position=position,
            text=paragraph_text,
            content_hash=paragraph_hash,
            fingerprint=paragraph_hash[:24],
            keywords=", ".join(extract_keywords(paragraph_text, 8)),
            word_count=len(tokenize(paragraph_text)),
        ))
    return document


def document_summary(document: AcademicDocument) -> dict:
    return {
        "id": document.id,
        "document_id": document.document_id,
        "filename": document.filename,
        "title": document.title,
        "student_name": document.student_name,
        "usn": document.usn,
        "department": document.department,
        "semester": document.semester,
        "subject": document.subject,
        "project_type": document.project_type,
        "keywords": document.keywords.split(", ") if document.keywords else [],
        "word_count": document.word_count,
        "page_count": document.page_count,
        "version": document.version,
        "approval_status": document.approval_status,
        "is_archived": document.is_archived,
        "similarity_score": document.similarity_score,
        "ai_score": document.ai_score,
        "created_at": document.created_at.isoformat(),
    }
