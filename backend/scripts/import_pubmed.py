from pathlib import Path

from pathlib import Path



from sqlalchemy.orm import Session

from backend.app.database import SessionLocal
from backend.app.services.repository import add_document

DATA_FOLDER = Path("backend/healthcare_datasets/pubmed")
def import_papers():
    db: Session = SessionLocal()

    files = list(DATA_FOLDER.glob("*.txt"))

    print(f"Found {len(files)} papers")

    imported = 0

    for file in files:
        try:
            text = file.read_text(encoding="utf-8").strip()

            if len(text) < 500:
                continue

            add_document(
                db=db,
                filename=file.name,
                raw_text=text,
                text=text,
                metadata={
                    "title": file.stem,
                    "department": "Healthcare",
                    "project_type": "Research Paper",
                    "language": "en",
                },
            )

            imported += 1

            if imported % 25 == 0:
                db.commit()
                print(f"Imported {imported} papers...")

        except Exception as e:
            print(file.name, e)

    db.commit()

    print(f"\nSuccessfully imported {imported} papers.")

    db.close()

if __name__ == "__main__":
    import_papers()    