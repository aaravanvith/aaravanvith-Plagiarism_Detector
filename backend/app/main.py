from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel

from .database import init_db, get_db, Report
from .services.extract import extract_text
from .services.preprocessing import clean_text
from .services.similarity import analyze_document
from .services.ai_detection import detect_ai_content
from .services import correction_agent as ca

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
        "flagged_sentences": [
            {
                "sentence": m.sentence,
                "similarity": m.best_score,
                "matched_source": m.best_source,
                "matched_text": m.best_source_sentence,
                "risk": m.risk,
            }
            for m in flagged
        ],
        "all_sentences": [
            {
                "sentence": m.sentence,
                "similarity": m.best_score,
                "risk": m.risk,
                "flagged": m.flagged,
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
