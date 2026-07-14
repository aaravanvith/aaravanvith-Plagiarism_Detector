from pathlib import Path

from sqlalchemy import Boolean, create_engine, Column, ForeignKey, Integer, String, Float, Text, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "app.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    student_name = Column(String, nullable=True)
    usn = Column(String, nullable=True)
    text = Column(Text, nullable=False)
    plagiarism_score = Column(Float, nullable=False)
    verdict = Column(String, nullable=False)
    ai_probability = Column(Float, nullable=False)
    ai_label = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class AcademicDocument(Base):
    """Repository record kept separate from the legacy report workflow."""
    __tablename__ = "academic_documents"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(String, unique=True, nullable=False, index=True)
    source_report_id = Column(Integer, ForeignKey("reports.id"), nullable=True, index=True)
    filename = Column(String, nullable=False)
    title = Column(String, nullable=True, index=True)
    student_name = Column(String, nullable=True, index=True)
    usn = Column(String, nullable=True, index=True)
    department = Column(String, nullable=True, index=True)
    branch = Column(String, nullable=True)
    semester = Column(String, nullable=True, index=True)
    subject = Column(String, nullable=True, index=True)
    guide = Column(String, nullable=True)
    college = Column(String, nullable=True)
    academic_year = Column(String, nullable=True)
    project_type = Column(String, nullable=True)
    language = Column(String, default="en")
    text = Column(Text, nullable=False)
    abstract = Column(Text, nullable=True)
    keywords = Column(Text, nullable=True)
    content_hash = Column(String, nullable=False, index=True)
    word_count = Column(Integer, default=0)
    page_count = Column(Integer, default=0)
    reference_count = Column(Integer, default=0)
    figures_count = Column(Integer, default=0)
    tables_count = Column(Integer, default=0)
    ai_score = Column(Float, nullable=True)
    similarity_score = Column(Float, nullable=True)
    novelty_score = Column(Float, nullable=True)
    approval_status = Column(String, default="pending", index=True)
    version = Column(Integer, default=1)
    is_archived = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DocumentParagraph(Base):
    """Paragraph-level searchable units; embeddings can be attached later."""
    __tablename__ = "document_paragraphs"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("academic_documents.id"), nullable=False, index=True)
    position = Column(Integer, nullable=False)
    section = Column(String, nullable=True)
    text = Column(Text, nullable=False)
    content_hash = Column(String, nullable=False, index=True)
    fingerprint = Column(String, nullable=False, index=True)
    keywords = Column(Text, nullable=True)
    word_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
