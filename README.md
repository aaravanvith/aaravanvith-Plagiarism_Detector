# VTU Report Plagiarism Detector

A full-stack plagiarism detector for academic reports. The React/Vite frontend
works with a FastAPI, SQLite, scikit-learn backend and optional semantic
similarity. It analyzes PDF, DOCX, TXT, Markdown, and RTF uploads, identifies
matching passages, records report history, and can produce corrected copies.
Corrected-file export supports PDF, DOCX, TXT, and Markdown uploads.

## What is included in Git

Everything required for a basic local run is tracked: application source,
Python requirements, the frontend lockfile, a starter reference corpus, and
`backend/data/.gitkeep` for runtime data.

These local files are intentionally **not** tracked and are created or copied
after cloning:

- `backend/.env` and `frontend/.env` - local configuration and secrets
- `backend/data/app.db` - SQLite database, created on backend startup
- `backend/data/ai_detector.joblib` - generated AI-detection model
- `backend/reference_corpus/chromadb/` - optional generated Chroma vector store
- Python virtual environments, `frontend/node_modules`, build output, and logs

Use the committed templates [backend/.env.example](backend/.env.example) and
[frontend/.env.example](frontend/.env.example); do not commit real API keys.

## Prerequisites

- Git
- Python 3.10, 3.11, or 3.12, with `pip`
- Node.js 20.19+ (or 22.12+) and npm

Optional: [Ollama](https://ollama.com/) for higher-quality local rewrite
suggestions, and a CORE API key for importing academic papers.

deactivate
cd ..
Rename-Item .\venv .\venv-py314
py -3.10 -m venv venv
.\venv\Scripts\Activate.ps1
python --version

## Run after cloning

Clone the repository and open its root directory:

```bash
git clone <repository-url>
cd plagiarism-detector
```

### 1. Start the backend

Open a terminal in the repository root, then enter `backend`.

**Windows PowerShell**

```powershell
cd backend
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -m uvicorn app.main:app --reload --port 8000
```

If PowerShell blocks the activation script, run the following once in that
terminal, then activate it again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

**macOS/Linux**

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
python -m uvicorn app.main:app --reload --port 8000
```

The API is ready when `http://localhost:8000/api/health` returns a successful
response. Interactive API documentation is at `http://localhost:8000/docs`.
Keep this terminal running.

### 2. Start the frontend

Open a **second** terminal in the repository root:

**Windows PowerShell**

```powershell
cd frontend
npm ci
Copy-Item .env.example .env
npm run dev
```

**macOS/Linux**

```bash
cd frontend
npm ci
cp .env.example .env
npm run dev
```

Open the URL printed by Vite, normally `http://localhost:5173`.
`frontend/.env` already points to the local API. Change `VITE_API_URL` only
when the backend runs on another host or port, then restart Vite.

## First-run behavior

- Backend startup creates `backend/data/app.db` automatically.
- The first analysis creates `backend/data/ai_detector.joblib` automatically.
- With `ENABLE_SEMANTIC_SIMILARITY=true` (the default), the first analysis may
  download the `all-MiniLM-L6-v2` sentence-transformer model. For an entirely
  offline initial run, set `ENABLE_SEMANTIC_SIMILARITY=false` in `backend/.env`
  before starting the backend. TF-IDF/cosine analysis still works.
- Sample documents in `backend/reference_corpus/` are used immediately as the
  comparison corpus. Add your own `.txt` references there and restart the
  backend to load them. The optional Chroma database is generated separately
  and is not required by the web app.

## Optional services

### Local Ollama rewrites

The correction agent works without any service using a built-in fallback. To
enable local model rewrites, install Ollama, ensure it is running, and run:

```bash
ollama pull gemma2:2b
```

Set `OLLAMA_MODEL` in `backend/.env` if you use a different installed model.

### CORE academic-paper importer

Add a valid `CORE_API_KEY` to `backend/.env`, restart the backend, and use the
repository import feature or its API endpoint. This is optional; normal local
analysis needs no API key.

## Useful commands

Run these from the stated directory after activating the backend environment
where applicable.

```bash
# Backend health check (repository root; PowerShell)
Invoke-WebRequest http://localhost:8000/api/health

# Frontend production build (frontend directory)
npm run build

# Create/update the backend database schema (backend directory)
python scripts/migrate.py
```

The `backend/scripts/download_pubmed.py`, `import_pubmed.py`, and
`build_database.py` utilities are optional corpus-maintenance tools. They are
not required to run the web application.

## Main API endpoints

- `POST /api/analyze` - analyze an uploaded report
- `POST /api/correct` and `POST /api/auto-correct` - create/apply corrections
- `POST /api/chat` - ask the correction assistant about an analysis
- `GET /api/reports` - report history
- `GET /api/reports/{report_id}` and `DELETE /api/reports/{report_id}` - view or delete a report
- `POST /api/repository/documents` - add a reference document
- `GET /api/repository/documents` and `GET /api/repository/stats` - browse local references and statistics
- `POST /api/repository/documents/{document_id}/archive` and `/restore` - manage a reference document
- `GET /api/repository/core/status` and `POST /api/repository/core/import` - check or import from CORE
- `GET /api/health` - health check

## Project layout

```text
backend/
  app/                 FastAPI application and analysis services
  data/                Generated SQLite database and local model (ignored)
  reference_corpus/    Tracked starter comparison documents; generated Chroma data is ignored
  .env.example         Backend configuration template
  requirements.txt     Python dependencies
frontend/
  src/                 React application
  .env.example         Frontend configuration template
  package-lock.json    Pinned npm dependency tree
  package.json         npm scripts and dependencies
```
