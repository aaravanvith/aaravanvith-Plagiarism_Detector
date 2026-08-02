from pathlib import Path
import chromadb
from chromadb.utils import embedding_functions

DATA_FOLDER = Path("backend/healthcare_datasets/pubmed")
DB_FOLDER = "backend/reference_corpus/chromadb"

client = chromadb.PersistentClient(path=DB_FOLDER)

embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2"
)

collection = client.get_or_create_collection(
    name="pubmed_papers",
    embedding_function=embedding_function
)

from uuid import uuid4

files = list(DATA_FOLDER.glob("*.txt"))

print(f"Found {len(files)} files")

for file in files:
    text = file.read_text(encoding="utf-8")

    collection.add(
        ids=[str(uuid4())],
        documents=[text],
        metadatas=[{"source": file.name}]
    )

print("Offline database created successfully!")