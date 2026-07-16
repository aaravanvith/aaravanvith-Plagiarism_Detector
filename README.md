# Plagiarism Detector — VTU Report Plagiarism Detector

A full-stack implementation of the Major Project (BCI685) described in
`Major_Project_3.pptx`: an **offline, explainable, ML-based plagiarism
detector for VTU project reports**, extended with the Phase‑2 features
(AI‑generated content detection and a Correction Agent).

---

## 1. How this maps to your presentation

| Slide | Requirement | Where it's implemented |
|---|---|---|
| 6 — ML Component | TF‑IDF + Cosine Similarity | `backend/app/services/similarity.py` (scikit-learn `TfidfVectorizer` + `cosine_similarity`) |
| 6 — GenAI (dev-support only) | Not used to assess submissions | No LLM API is called at analysis time — everything is scikit-learn / rule-based, satisfying "GenAI is not used to assess or alter student submissions" |
| 7 — Differentiators | Offline, explainable, VTU-specific | No internet calls at runtime; every score traces to a specific matched sentence + source |
| 8 — Block Diagram | Documents → Preprocessing → ML Analysis → Output % | `extract.py` → `preprocessing.py` → `similarity.py` → `/api/analyze` response |
| 12 — AI vs Human Detection | Stylometric AI-content classifier | `backend/app/services/ai_detection.py` (trained `LogisticRegression` over sentence-length burstiness, lexical diversity, stop-word ratio, punctuation variety) |
| 13/14 — Correction Agent | Detect → Explain → Correct, chatbot | `backend/app/services/correction_agent.py` + `CorrectionPanel.jsx` (explanation, rewrite, APA/IEEE citation, chat) |
| 16 — Sample Output | Score, flagged sentence, rewrite, citation | The results dashboard + Correction Agent panel reproduce this exact flow |

---

## 2. Architecture

```
 ┌────────────────────┐        REST/JSON        ┌──────────────────────────┐
 │   React (Vite) UI   │  ───────────────────▶   │   FastAPI backend        │
 │  - Upload           │  ◀───────────────────   │  - extract (pdf/docx/txt)│
 │  - Score dashboard  │                          │  - preprocessing         │
 │  - Correction Agent │                          │  - TF-IDF + cosine sim   │
 │  - History          │                          │  - AI-content classifier │
 └────────────────────┘                           │  - Correction Agent      │
                                                    │  - SQLite persistence    │
                                                    └──────────────────────────┘
```

- **Backend**: FastAPI + scikit-learn + SQLAlchemy/SQLite. No external ML
  API keys required — the whole pipeline runs offline.
- **Frontend**: React 19 + Vite + Tailwind CSS.
- **Database**: SQLite (`backend/data/app.db`, created automatically). Every
  analyzed report is also added to the comparison corpus, so it doubles as
  a growing cross-student similarity check — exactly the "university-specific"
  differentiator from Slide 7.

### Optional hybrid similarity

The plagiarism engine keeps the original TF-IDF/cosine workflow and adds an
optional SBERT semantic score. For every matched sentence, the API returns
`tfidf_similarity`, `cosine_similarity`, `semantic_similarity`, and
`hybrid_similarity`. When SBERT is available, the hybrid score is the average
of those three signals; if it is disabled or cannot load, scoring safely falls
back to the original TF-IDF cosine result.

Install the updated backend dependencies before running the enhancement:

```bash
pip install -r requirements.txt
```

On its first enabled analysis, Sentence Transformers downloads the public
`all-MiniLM-L6-v2` model (about 80–90 MB; no API key, account, or GPU needed).
Set `ENABLE_SEMANTIC_SIMILARITY=false` to disable this enhancement and keep
the original offline-only comparison path. `SEMANTIC_MODEL_NAME` can override
the default model.

### Academic repository foundation

The local repository now stores both legacy analyzed reports and faculty-added
reference documents without changing the existing `/api/analyze` or report
history APIs. SQLite development tables include academic metadata, document
hashes, version number, approval/archive state, and separately indexed
paragraph records with fingerprints and keywords. Existing data remains
untouched because the schema addition is additive.

Repository endpoints:

- `POST /api/repository/documents` — add PDF, DOCX, TXT, Markdown, or RTF
  reference material with optional academic metadata.
- `GET /api/repository/documents?q=&department=&subject=` — search/filter
  local documents.
- `GET /api/repository/stats` — local document, paragraph, and word totals.
- `POST /api/repository/documents/{id}/archive` and `/restore` — reversible
  repository management.

To create the new tables explicitly, run `python scripts/migrate.py` from the
`backend` directory. This needs no API key, cloud account, or external service.

### Optional CORE academic-paper importer

CORE can supply open-access research papers to the local reference repository.
It is optional: normal plagiarism analysis remains fully offline. Create or
update `backend/.env` with a regenerated `CORE_API_KEY`; never commit or paste
that value. The API exposes no endpoint that returns the key. Use
`POST /api/repository/core/import?query=<topic>&limit=5` to import a
small, rate-limited set of matching papers, then those papers participate in
future local comparisons. CORE is used as a corpus provider, not as the model
training database.

---

## 3. Setup

### Backend

```bash
cd backend
python3 -m venv venv && source venv/bin/activate   # optional but recommended
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

The API is now at `http://localhost:8000` (interactive docs at `/docs`).
A small reference corpus of sample academic paragraphs ships in
`backend/reference_corpus/` so you get meaningful results immediately —
add your own past student reports there (as `.txt`) for a real deployment.

### Optional Gemini rewriting

The Correction Agent produces independent **Academic**, **Human**, and
**Simple** rewrites. Gemini is selected when `GEMINI_API_KEY` is configured;
otherwise the service uses `OPENAI_API_KEY`, then uses its local structural
rewriter only when neither provider is configured.

Add the following to `backend/.env` (never commit the key):

```env
GEMINI_API_KEY=your-gemini-api-key
GEMINI_REWRITE_MODEL=gemini-3.5-flash
```

The official `google-genai` SDK is included in `backend/requirements.txt`.
A configured Gemini or OpenAI provider returns an error if it cannot generate
a valid rewrite; it does not silently switch to the offline fallback.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. It talks to the backend at the URL in
`frontend/.env` (`VITE_API_URL`, defaults to `http://localhost:8000`).

---

## 4. Using it

1. **Analyze** — upload a `.pdf`, `.docx`, or `.txt` report (optionally with
   student name/USN). You'll get:
   - An overall plagiarism percentage + risk verdict (seal-style gauge)
   - AI-generated-content likelihood with the stylometric features behind it
   - A sentence-by-sentence breakdown; flagged lines are highlighted
2. **Click any flagged sentence** to open the **Correction Agent**:
   - *Explain* — why it was flagged, and against which source
   - *Correct* — a rule-based rewrite suggestion
   - *Citation* — an APA and IEEE citation template
   - *Chat* — ask "Why is this flagged?" / "Can you rewrite this?" / "How do I cite this?"
3. **Submission History** — every analyzed report, with delete support.

---

## 5. Notes for your viva / defense

- **Why TF‑IDF + cosine similarity, not a transformer model?** It's fast,
  fully explainable (you can point to the exact overlapping n‑grams), and
  runs with zero GPU/internet dependency — directly satisfying the
  "offline-capable, explainable" requirement in your problem statement.
- **Why is the AI-detector a small LogisticRegression, not a downloaded
  detector?** Pretrained AI-text detectors require downloading model
  weights from the internet, which conflicts with the offline requirement.
  Instead, a compact classifier is trained on well-documented stylometric
  signatures of LLM output (low sentence-length burstiness, high lexical
  uniformity) — transparent and reproducible, and it's a real `fit()` call,
  not a hard-coded rule.
- **How does the Correction Agent rewrite text?** Gemini and OpenAI generate
  independent Academic, Human, and Simple rewrites when their respective API
  keys are configured. A structural offline fallback is retained for local
  demonstrations without a rewrite-provider key.
- **Current Correction Agent provider:** Gemini is preferred when
  `GEMINI_API_KEY` is configured; otherwise OpenAI is used when
  `OPENAI_API_KEY` is available. The local structural rewriter is used only
  when neither provider is configured.
- **Extending it**: swap `reference_corpus/*.txt` for your department's
  real past submissions, tune `FLAG_THRESHOLD`/`HIGH_RISK_THRESHOLD` in
  `similarity.py`, or add authenticated faculty logins to `main.py`.

---

## 6. Project structure

```
plagiarism-detector/
├── backend/
│   ├── app/
│   │   ├── main.py                # FastAPI routes
│   │   ├── database.py            # SQLAlchemy models (SQLite)
│   │   └── services/
│   │       ├── extract.py         # pdf/docx/txt → raw text
│   │       ├── preprocessing.py   # cleaning, sentence split, stylometrics
│   │       ├── similarity.py      # TF-IDF + cosine similarity engine
│   │       ├── ai_detection.py    # AI-vs-human classifier
│   │       └── correction_agent.py# explain / rewrite / cite / chat
│   ├── reference_corpus/          # sample comparison documents
│   └── requirements.txt
└── frontend/
    ├── src/
    │   ├── components/            # UploadPanel, ScoreSeal, SentenceReport,
    │   │                          # AIDetectionCard, CorrectionPanel, HistoryTable
    │   ├── api.js                 # backend client
    │   └── App.jsx
    └── package.json
```
