from pathlib import Path
import logging
import shutil
import threading
import re
from time import perf_counter

from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Form, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel

from .database import AcademicDocument, DocumentParagraph, init_db, get_db, Report, SessionLocal
from .services.extract import extract_text
from .services.preprocessing import clean_text
from .services.similarity import analyze_document
from .services.semantic_similarity import invalidate_reference_embedding_cache
from .services.ai_detection import detect_ai_content
from .services import correction_agent as ca
from .services.document_correction import (
    CorrectionValidationError, create_corrected_file, parse_corrections,
)
from .services.core_client import CoreConfigurationError, CoreRequestError, configured as core_configured, search_works
from .services.repository import add_document, content_hash, document_summary

REFERENCE_CORPUS_DIR = Path(__file__).resolve().parent.parent / "reference_corpus"
HEALTHCARE_CORPUS_DIR = Path(__file__).resolve().parent.parent / "healthcare_datasets" / "pubmed"
logger = logging.getLogger(__name__)

app = FastAPI(title="VTU Report Plagiarism Detector API", version="1.0.0")

@app.middleware("http")
async def report_unexpected_errors(request, call_next):
    try:
        return await call_next(request)
    except Exception:
        logger.exception("Unhandled API error for %s", request.url.path)
        return JSONResponse(status_code=500, content={
            "detail": "The backend could not complete this request. Check the Render logs for the error details."
        })

# Keep CORS outside the error middleware so browsers can read error responses.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Applied-Corrections", "X-Skipped-Corrections"],
)

HEALTHCARE_KEYWORDS = [
    "health", "healthcare", "medical", "medicine",
    "hospital", "patient", "doctor", "clinical",
    "diagnosis", "treatment", "disease", "covid",
    "diabetes", "cancer", "blood", "heart"
]

def is_healthcare_report(text: str) -> bool:
    text = text.lower()
    matches = sum(1 for word in HEALTHCARE_KEYWORDS if word in text)
    return matches >= 3


@app.on_event("startup")
def on_startup():
    init_db()
    db = SessionLocal()
    try:
        _reference_corpus_cache.rebuild(db)
    finally:
        db.close()



class ReferenceCorpusCache:
    """Cache static references while retaining prior student reports dynamically."""

    def __init__(self):
        self._lock = threading.RLock()
        self._corpus: dict[str, str] | None = None

    def rebuild(self, db: Session) -> None:
        corpus: dict[str, str] = {}
        for source_file in REFERENCE_CORPUS_DIR.glob("*.txt"):
            corpus[source_file.stem] = source_file.read_text(encoding="utf-8", errors="ignore")
        # Bundled healthcare references must work on a fresh database too.
        # SQLite imports are optional and may be lost when hosting restarts.
        for source_file in sorted(HEALTHCARE_CORPUS_DIR.glob("*.txt")):
            text = source_file.read_text(encoding="utf-8", errors="ignore").strip()
            if text:
                corpus[f"pubmed::{source_file.stem}"] = text
        known_content = {content_hash(text) for text in corpus.values()}
        for document in db.query(AcademicDocument).filter(
            AcademicDocument.source_report_id.is_(None),
            AcademicDocument.is_archived.is_(False),
        ).all():
            fingerprint = content_hash(document.text)
            if fingerprint not in known_content:
                corpus[f"repository::{document.title or document.filename}"] = document.text
                known_content.add(fingerprint)
        with self._lock:
            self._corpus = corpus
        invalidate_reference_embedding_cache()
        logger.info("Reference corpus cache rebuilt with %d static sources", len(corpus))

    def invalidate(self) -> None:
        with self._lock:
            self._corpus = None
        invalidate_reference_embedding_cache()

    def static_corpus(self, db: Session) -> dict[str, str]:
        with self._lock:
            cached = self._corpus
        if cached is None:
            self.rebuild(db)
            with self._lock:
                cached = self._corpus
        return dict(cached or {})


_reference_corpus_cache = ReferenceCorpusCache()


def invalidate_reference_corpus_cache() -> None:
    _reference_corpus_cache.invalidate()


def load_reference_corpus(db: Session, current_filename: str = "") -> dict[str, str]:
    """
    Load only the repository/reference documents.
    Do NOT compare against previous student submissions.
    """
    corpus = _reference_corpus_cache.static_corpus(db)

    print("=" * 80)
    print("REFERENCE CORPUS")
    print("=" * 80)
    print("Total sources:", len(corpus))

    count = 0
    for key in corpus.keys():
        print(key)
        count += 1
        if count >= 20:
            break

    return corpus

def build_online_corpus(text: str) -> dict[str, str]:
    """
    Dynamically retrieve relevant academic documents from CORE.

    CORE results are fetched page-by-page. There is no fixed total-paper
    limit such as 5 or 20.

    A lightweight relevance check is applied before a CORE document is
    added to the expensive TF-IDF/SBERT analysis. If two consecutive
    CORE
    pages contain no relevant usable documents, retrieval stops early.
    """

    words = re.findall(r"[A-Za-z]{4,}", text.lower())

    stop_words = {
        "this", "that", "with", "from", "which", "their",
        "have", "been", "were", "will", "using", "used",
        "into", "about", "these", "those", "there", "also",
        "than", "then", "they", "them", "such", "more",
        "other", "only", "each", "where", "when", "what",
        "healthcare", "medical", "research", "study",
        "report", "abstract", "presents", "system",
        "project", "paper", "based", "results",
        "method", "methods", "data", "analysis",
    }

    frequencies = {}

    for word in words:
        if word in stop_words:
            continue

        frequencies[word] = frequencies.get(word, 0) + 1

    keywords = [
        word
        for word, _count in sorted(
            frequencies.items(),
            key=lambda item: item[1],
            reverse=True,
        )[:5]
    ]

    healthcare_terms = [
        "patient",
        "monitoring",
        "health",
        "hospital",
        "clinical",
        "diagnosis",
        "treatment",
        "disease",
        "healthcare",
        "medical",
    ]

    for term in healthcare_terms:
        if term in words and term not in keywords:
            keywords.append(term)

    keywords = keywords[:6]

    if not keywords:
        logger.warning(
            "Online mode: could not create a search query."
        )
        return {}

    query = " ".join(keywords)

    print(">>> CORE SEARCH QUERY:", query)

    online_corpus: dict[str, str] = {}

    print(">>> BUILDING RELEVANCE-FILTERED ONLINE CORPUS")

    page_size = 10
    offset = 0
    total_hits = None
    page_number = 1

    # If two consecutive pages contain no relevant papers,
    # additional CORE results are unlikely to be useful for this report.
    consecutive_empty_pages = 0
    max_consecutive_empty_pages = 2

    # Minimum fraction of query keywords that should appear in
    # the title/abstract/available text for a document to be considered
    # relevant enough for the expensive ML comparison.
    relevance_threshold = 0.34

    while True:

        try:
            print(
                f">>> CORE PAGE {page_number}: "
                f"offset={offset}, page_size={page_size}"
            )

            works, current_total_hits = search_works(
                query,
                limit=page_size,
                offset=offset,
            )

            if total_hits is None:
                total_hits = current_total_hits
                print(
                    ">>> CORE TOTAL HITS:",
                    total_hits,
                )

            print(
                f">>> CORE PAGE {page_number} RETURNED: "
                f"{len(works)} papers"
            )

        except CoreConfigurationError as exc:
            logger.warning(
                "CORE is not configured: %s",
                exc,
            )
            break

        except CoreRequestError as exc:
            logger.warning(
                "CORE page failed at offset %d: %s",
                offset,
                exc,
            )

            # Retry the failed page with a smaller request.
            if page_size == 10:

                retry_page_size = 5

                print(
                    f">>> RETRYING CORE PAGE {page_number} "
                    f"WITH {retry_page_size} PAPERS"
                )

                try:
                    works, current_total_hits = search_works(
                        query,
                        limit=retry_page_size,
                        offset=offset,
                    )

                    if total_hits is None:
                        total_hits = current_total_hits
                        print(
                            ">>> CORE TOTAL HITS:",
                            total_hits,
                        )

                    print(
                        f">>> CORE RETRY PAGE {page_number} "
                        f"RETURNED: {len(works)} papers"
                    )

                except CoreConfigurationError as retry_exc:
                    logger.warning(
                        "CORE is not configured during retry: %s",
                        retry_exc,
                    )
                    break

                except CoreRequestError as retry_exc:
                    logger.warning(
                        "CORE retry failed at offset %d: %s",
                        offset,
                        retry_exc,
                    )
                    break

            else:
                break

        if not works:
            print(
                ">>> CORE returned no more papers."
            )
            break

        relevant_on_page = 0

        for index, work in enumerate(
            works,
            start=1,
        ):

            if not work.text:
                continue

            if len(work.text.split()) < 20:
                continue

            # Use title + the beginning of the document for the
            # lightweight relevance check. This avoids scanning
            # enormous full-text documents just to determine relevance.
            preview_text = (
                f"{work.title or ''}\n"
                f"{work.text[:5000]}"
            ).lower()

            matched_keywords = sum(
                1
                for keyword in keywords
                if keyword.lower() in preview_text
            )

            relevance_score = (
                matched_keywords / len(keywords)
                if keywords
                else 0.0
            )

            print(
                f">>> CORE PAPER: "
                f"relevance={relevance_score:.2f} "
                f"title={work.title[:80] if work.title else 'Untitled'}"
            )

            if relevance_score < relevance_threshold:
                continue

            relevant_on_page += 1

            # Limit individual document size so one very large
            # CORE paper does not make the ML matrix unnecessarily large.
            work_text = work.text[:20000]

            title = (
                work.title
                or f"CORE Online Paper {offset + index}"
            )

            if work.doi:
                source_name = (
                    f"online::CORE::{work.doi}"
                )
            else:
                source_name = (
                    f"online::CORE::{offset + index}::{title[:60]}"
                )

            if source_name not in online_corpus:
                online_corpus[source_name] = work_text

        print(
            f">>> CORE PAGE {page_number}: "
            f"{relevant_on_page} relevant papers kept"
        )

        if relevant_on_page == 0:
            consecutive_empty_pages += 1

            print(
                f">>> NO RELEVANT PAPERS ON THIS PAGE "
                f"({consecutive_empty_pages}/"
                f"{max_consecutive_empty_pages})"
            )
        else:
            consecutive_empty_pages = 0

        if (
            consecutive_empty_pages
            >= max_consecutive_empty_pages
        ):
            print(
                ">>> CORE: stopping because consecutive pages "
                "contain no relevant papers."
            )
            break

        offset += len(works)
        page_number += 1

        if (
            total_hits is not None
            and offset >= total_hits
        ):
            print(
                ">>> CORE: all available results retrieved."
            )
            break

        if len(works) < page_size:
            print(
                ">>> CORE returned a partial final page."
            )
            break

    print(
        ">>> CORE ONLINE DOCUMENTS USED:",
        len(online_corpus),
    )

    logger.info(
        "ONLINE SEARCH: dynamically retrieved %d "
        "relevant documents",
        len(online_corpus),
    )

    return online_corpus


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/analyze")
def analyze(
    file: UploadFile = File(...),
    student_name: str = Form(""),
    usn: str = Form(""),
    online: bool = Form(False),
    db: Session = Depends(get_db),
):
    analysis_started = perf_counter()

    print(">>> ONLINE FLAG RECEIVED BY BACKEND:", online)
    
    content = file.file.read()
    if not content:
        raise HTTPException(400, "Empty file uploaded")

    extraction_started = perf_counter()
    raw_text = extract_text(file.filename, content)
    logger.info("Text extraction completed in %.3fs", perf_counter() - extraction_started)
    text = clean_text(raw_text)

    if len(text.split()) < 20:
        raise HTTPException(400, "Could not extract enough text from this file (need 20+ words)")

    print(is_healthcare_report(text))

    if not is_healthcare_report(text):
        raise HTTPException(
            status_code=400,
            detail="Only healthcare-related reports are supported in this prototype."
    )

    corpus_started = perf_counter()

    local_corpus = load_reference_corpus(db, file.filename)

    if online:
        online_corpus = build_online_corpus(text)

        corpus = {
            **local_corpus,
            **online_corpus,
        }

        logger.info(
            "ONLINE ANALYSIS: local=%d + online=%d = total=%d",
            len(local_corpus),
            len(online_corpus),
            len(corpus),
        )
    else:
        online_corpus = {}
        corpus = local_corpus

        logger.info(
            "OFFLINE ANALYSIS: local=%d + online=0 = total=%d",
            len(local_corpus),
            len(corpus),
        )

    logger.info(
        "Corpus loading completed in %.3fs",
        perf_counter() - corpus_started,
    )


    sim_report = analyze_document(raw_text, corpus)
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

    #add_document(
    #   db,
    #   filename=file.filename,
    #   raw_text=raw_text,
    #   text=text,
    #   metadata={"student_name": student_name or None, "usn": usn or None},
    #   source_report_id=record.id,
    #   ai_score=ai_report["ai_probability"],
    #   similarity_score=sim_report.overall_score,
    #)
    #db.commit()
    # The report is intentionally not part of the persistent corpus cache, but
    # it is a reference on the next request so invalidate assembled matrices.
    invalidate_reference_embedding_cache()
    logger.info("Total analysis completed in %.3fs", perf_counter() - analysis_started)

    flagged = [m for m in sim_report.sentence_matches if m.flagged]

    return {
        "report_id": record.id,
        "filename": file.filename,
        "plagiarism_score": sim_report.overall_score,
        "verdict": sim_report.verdict,
        "total_sources_compared": len(sim_report.sources_used),
        "sources_compared": sim_report.sources_used[:10],
        "analysis_mode": "online" if online else "offline",
        "local_sources_compared": len(local_corpus),
        "online_sources_compared": len(online_corpus),
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
                "start_offset": m.start_offset,
                "end_offset": m.end_offset,
            }
            for m in flagged
        ],
        "all_sentences": [
            {
                "sentence": m.sentence,
                "similarity": m.best_score,
                # The correction panel is opened from this list, so retain
                # the match context required by the correction/chat endpoints.
                "matched_source": m.best_source,
                "matched_text": m.best_source_sentence,
                "risk": m.risk,
                "flagged": m.flagged,
                "ai_probability": detect_ai_content(m.sentence)["ai_probability"] if len(m.sentence.split()) >= 8 else None,
                "ai_assessment_method": "experimental_synthetic_stylometry",
                "tfidf_similarity": m.tfidf_score,
                "cosine_similarity": m.cosine_score,
                "semantic_similarity": m.semantic_score,
                "hybrid_similarity": m.hybrid_score,
                "start_offset": m.start_offset,
                "end_offset": m.end_offset,
            }
            for m in sim_report.sentence_matches
        ],
        "extracted_text": raw_text,
    }


class CorrectRequest(BaseModel):
    sentence: str
    matched_source: str
    similarity: float
    rewrite_strength: str = "moderate"
    start_offset: int | None = None
    end_offset: int | None = None


@app.post("/api/correct")
def correct(req: CorrectRequest):
    try:
        response = ca.correct_sentence(req.sentence, req.matched_source, req.similarity, strength=req.rewrite_strength)
        response["start_offset"] = req.start_offset
        response["end_offset"] = req.end_offset
        return response
    except ca.RewriteProviderConfigurationError as exc:
        raise HTTPException(503, str(exc)) from exc


@app.post("/api/auto-correct")
async def auto_correct(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    corrections: str = Form(...),
):
    content = await file.read()
    if not content:
        raise HTTPException(422, "The uploaded file could not be processed.")
    try:
        correction_list = parse_corrections(corrections)
        output, download_name, media_type, summary = create_corrected_file(
    file.filename,
    content,
    correction_list,
)
    except CorrectionValidationError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(422, str(exc)) from exc

    background_tasks.add_task(shutil.rmtree, output.parent, ignore_errors=True)
    # FileResponse streams the separately-generated copy; the source upload is
    # never changed on disk or in the database.
    return FileResponse(
        output,
        media_type=media_type,
        filename=download_name,
        headers={
            "X-Applied-Corrections": str(summary["applied"]),
            "X-Skipped-Corrections": str(len(summary["skipped"])),
        },
    )


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
    invalidate_reference_embedding_cache()
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
    invalidate_reference_corpus_cache()
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
        works, total_hits = search_works(
            query,
            limit=min(limit, 10),
            offset=0,
        )
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
    invalidate_reference_corpus_cache()

    return {
        "query": query,
        "imported_count": len(imported),
        "documents": imported,
        "total_hits": total_hits,
    }


@app.post("/api/repository/documents/{document_id}/archive")
def archive_repository_document(document_id: int, db: Session = Depends(get_db)):
    document = db.query(AcademicDocument).filter(AcademicDocument.id == document_id).first()
    if not document:
        raise HTTPException(404, "Repository document not found")
    document.is_archived = True
    db.commit()
    invalidate_reference_corpus_cache()
    return {"archived": True}


@app.post("/api/repository/documents/{document_id}/restore")
def restore_repository_document(document_id: int, db: Session = Depends(get_db)):
    document = db.query(AcademicDocument).filter(AcademicDocument.id == document_id).first()
    if not document:
        raise HTTPException(404, "Repository document not found")
    document.is_archived = False
    db.commit()
    invalidate_reference_corpus_cache()
    return {"restored": True}
