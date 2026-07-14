from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel

from .database import AcademicDocument, DocumentParagraph, init_db, get_db, Report
from .services.extract import extract_text
from .services.preprocessing import clean_text
from .services.similarity import analyze_document
from .services.ai_detection import detect_ai_content
from .services import correction_agent as ca
from .services.core_client import CoreConfigurationError, CoreRequestError, configured as core_configured, search_works
from .services.repository import add_document, document_summary

REFERENCE_CORPUS_DIR = Path(__file__).resolve().parent.parent / "reference_corpus"

app = FastAPI(title="VTU Report Plagiarism Detector API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()


def load_reference_corpus(db: Session) -> dict[str, str]:
    corpus: dict[str, str] = {}
    for f in REFERENCE_CORPUS_DIR.glob("*.txt"):
        corpus[f.stem] = f.read_text(encoding="utf-8", errors="ignore")
    # also compare against previously submitted reports (cross-student check)
    for r in db.query(Report).all():
        corpus[f"prior_submission::{r.filename}"] = r.text
    # Standalone repository items (e.g. papers imported by faculty) are also
    # included while avoiding duplicate records created from legacy reports.
    for d in db.query(AcademicDocument).filter(AcademicDocument.source_report_id.is_(None), AcademicDocument.is_archived.is_(False)).all():
        corpus[f"repository::{d.title or d.filename}"] = d.text
    return corpus


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/analyze")
async def analyze(
    file: UploadFile = File(...),
    student_name: str = Form(""),
    usn: str = Form(""),
    db: Session = Depends(get_db),
):
    content = await file.read()
    if not content:
        raise HTTPException(400, "Empty file uploaded")

    raw_text = extract_text(file.filename, content)
    text = clean_text(raw_text)
    if len(text.split()) < 20:
        raise HTTPException(400, "Could not extract enough text from this file (need 20+ words)")

    corpus = load_reference_corpus(db)
    sim_report = analyze_document(text, corpus)
    ai_report = detect_ai_content(text)

    record = Report(
        filename=file.filename,
        student_name=student_name or None,
        usn=usn or None,
        text=text,
        plagiarism_score=sim_report.overall_score,
        verdict=sim_report.verdict,
        ai_probability=ai_report["ai_probability"],
        ai_label=ai_report["label"],
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    add_document(
        db,
        filename=file.filename,
        raw_text=raw_text,
        text=text,
        metadata={"student_name": student_name or None, "usn": usn or None},
        source_report_id=record.id,
        ai_score=ai_report["ai_probability"],
        similarity_score=sim_report.overall_score,
    )
    db.commit()

    flagged = [m for m in sim_report.sentence_matches if m.flagged]

    return {
        "report_id": record.id,
        "filename": file.filename,
        "plagiarism_score": sim_report.overall_score,
        "verdict": sim_report.verdict,
        "sources_compared": sim_report.sources_used,
        "total_sentences": len(sim_report.sentence_matches),
        "flagged_sentence_count": len(flagged),
        "ai_detection": ai_report,
        "similarity_method": {
            "name": "Hybrid similarity" if sim_report.semantic_available else "TF-IDF cosine fallback",
            "semantic_enabled": sim_report.semantic_enabled,
            "semantic_available": sim_report.semantic_available,
        },
        "flagged_sentences": [
            {
                "sentence": m.sentence,
                "similarity": m.best_score,
                "matched_source": m.best_source,
                "matched_text": m.best_source_sentence,
                "risk": m.risk,
                "tfidf_similarity": m.tfidf_score,
                "cosine_similarity": m.cosine_score,
                "semantic_similarity": m.semantic_score,
                "hybrid_similarity": m.hybrid_score,
            }
            for m in flagged
        ],
        "all_sentences": [
            {
                "sentence": m.sentence,
                "similarity": m.best_score,
                "risk": m.risk,
                "flagged": m.flagged,
                "tfidf_similarity": m.tfidf_score,
                "cosine_similarity": m.cosine_score,
                "semantic_similarity": m.semantic_score,
                "hybrid_similarity": m.hybrid_score,
            }
            for m in sim_report.sentence_matches
        ],
    }


class CorrectRequest(BaseModel):
    sentence: str
    matched_source: str
    similarity: float


@app.post("/api/correct")
def correct(req: CorrectRequest):
    return ca.correct_sentence(req.sentence, req.matched_source, req.similarity)


class ChatRequest(BaseModel):
    message: str
    sentence: str
    matched_source: str
    similarity: float


@app.post("/api/chat")
def chat(req: ChatRequest):
    reply = ca.chat_reply(
        req.message,
        {"sentence": req.sentence, "source": req.matched_source, "score": req.similarity},
    )
    return {"reply": reply}


@app.get("/api/reports")
def list_reports(db: Session = Depends(get_db)):
    reports = db.query(Report).order_by(Report.created_at.desc()).all()
    return [
        {
            "id": r.id,
            "filename": r.filename,
            "student_name": r.student_name,
            "usn": r.usn,
            "plagiarism_score": r.plagiarism_score,
            "verdict": r.verdict,
            "ai_probability": r.ai_probability,
            "ai_label": r.ai_label,
            "created_at": r.created_at.isoformat(),
        }
        for r in reports
    ]


@app.get("/api/reports/{report_id}")
def get_report(report_id: int, db: Session = Depends(get_db)):
    r = db.query(Report).filter(Report.id == report_id).first()
    if not r:
        raise HTTPException(404, "Report not found")
    return {
        "id": r.id,
        "filename": r.filename,
        "student_name": r.student_name,
        "usn": r.usn,
        "plagiarism_score": r.plagiarism_score,
        "verdict": r.verdict,
        "ai_probability": r.ai_probability,
        "ai_label": r.ai_label,
        "created_at": r.created_at.isoformat(),
    }


@app.delete("/api/reports/{report_id}")
def delete_report(report_id: int, db: Session = Depends(get_db)):
    r = db.query(Report).filter(Report.id == report_id).first()
    if not r:
        raise HTTPException(404, "Report not found")
    db.delete(r)
    db.commit()
    return {"deleted": True}


@app.post("/api/repository/documents")
async def upload_repository_document(
    file: UploadFile = File(...),
    title: str = Form(""),
    student_name: str = Form(""),
    usn: str = Form(""),
    department: str = Form(""),
    branch: str = Form(""),
    semester: str = Form(""),
    subject: str = Form(""),
    guide: str = Form(""),
    college: str = Form(""),
    academic_year: str = Form(""),
    project_type: str = Form("Research Paper"),
    db: Session = Depends(get_db),
):
    """Add a local reference document without changing the analysis route."""
    if not file.filename.lower().endswith((".pdf", ".docx", ".txt", ".md", ".markdown", ".rtf")):
        raise HTTPException(400, "Unsupported file type. Use PDF, DOCX, TXT, Markdown, or RTF.")
    content = await file.read()
    if not content:
        raise HTTPException(400, "Empty file uploaded")
    raw_text = extract_text(file.filename, content)
    text = clean_text(raw_text)
    if len(text.split()) < 4:
        raise HTTPException(400, "Could not extract enough searchable text from this file")
    document = add_document(
        db,
        filename=file.filename,
        raw_text=raw_text,
        text=text,
        metadata={
            "title": title or None, "student_name": student_name or None, "usn": usn or None,
            "department": department or None, "branch": branch or None, "semester": semester or None,
            "subject": subject or None, "guide": guide or None, "college": college or None,
            "academic_year": academic_year or None, "project_type": project_type or None,
        },
    )
    db.commit()
    db.refresh(document)
    return document_summary(document)


@app.get("/api/repository/documents")
def list_repository_documents(
    q: str = "",
    department: str = "",
    subject: str = "",
    include_archived: bool = False,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    query = db.query(AcademicDocument)
    if not include_archived:
        query = query.filter(AcademicDocument.is_archived.is_(False))
    if department:
        query = query.filter(AcademicDocument.department.ilike(f"%{department}%"))
    if subject:
        query = query.filter(AcademicDocument.subject.ilike(f"%{subject}%"))
    if q:
        pattern = f"%{q}%"
        query = query.filter(
            AcademicDocument.title.ilike(pattern) |
            AcademicDocument.filename.ilike(pattern) |
            AcademicDocument.student_name.ilike(pattern) |
            AcademicDocument.usn.ilike(pattern) |
            AcademicDocument.keywords.ilike(pattern)
        )
    documents = query.order_by(AcademicDocument.created_at.desc()).limit(min(max(limit, 1), 500)).all()
    return [document_summary(document) for document in documents]


@app.get("/api/repository/stats")
def repository_stats(db: Session = Depends(get_db)):
    documents = db.query(AcademicDocument).filter(AcademicDocument.is_archived.is_(False)).all()
    return {
        "total_documents": len(documents),
        "total_paragraphs": db.query(DocumentParagraph).count(),
        "total_words": sum(document.word_count for document in documents),
        "pending_approval": sum(document.approval_status == "pending" for document in documents),
    }


@app.get("/api/repository/core/status")
def core_status():
    """Return configuration state only; a secret is never sent to the client."""
    return {"configured": core_configured(), "provider": "CORE"}


@app.post("/api/repository/core/import")
def import_from_core(
    query: str,
    limit: int = 5,
    db: Session = Depends(get_db),
):
    """Import a small, rate-limited set of open-access CORE works locally."""
    try:
        works = search_works(query, limit)
    except CoreConfigurationError as exc:
        raise HTTPException(503, str(exc)) from exc
    except CoreRequestError as exc:
        raise HTTPException(502, str(exc)) from exc

    imported: list[dict] = []
    for work in works:
        text = clean_text(work.text)
        document = add_document(
            db,
            filename=f"core-{work.doi or work.title[:50]}.txt",
            raw_text=work.text,
            text=text,
            metadata={
                "title": work.title,
                "student_name": work.authors or None,
                "academic_year": work.year or None,
                "project_type": "Research Paper (CORE)",
            },
        )
        imported.append(document_summary(document))
    db.commit()
    return {"query": query, "imported_count": len(imported), "documents": imported}


@app.post("/api/repository/documents/{document_id}/archive")
def archive_repository_document(document_id: int, db: Session = Depends(get_db)):
    document = db.query(AcademicDocument).filter(AcademicDocument.id == document_id).first()
    if not document:
        raise HTTPException(404, "Repository document not found")
    document.is_archived = True
    db.commit()
    return {"archived": True}


@app.post("/api/repository/documents/{document_id}/restore")
def restore_repository_document(document_id: int, db: Session = Depends(get_db)):
    document = db.query(AcademicDocument).filter(AcademicDocument.id == document_id).first()
    if not document:
        raise HTTPException(404, "Repository document not found")
    document.is_archived = False
    db.commit()
    return {"restored": True}
