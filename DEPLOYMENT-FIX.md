# Deploy the connection fix

Upload the changed source files to the existing GitHub repository and redeploy
both connected services. This workspace currently has no `.git` directory,
so it cannot push changes as an existing checkout.

Changed application files:
- frontend/src/api.js
- frontend/src/components/UploadPanel.jsx
- frontend/src/components/HistoryTable.jsx
- backend/app/main.py

## Vercel

Use `frontend` as the root directory. Set `VITE_API_URL` to
`https://vidya-chaya-audit.onrender.com`, then redeploy so Vite includes the
setting in the production build. The same URL remains the fallback.

## Render

Use `backend` as the root directory.

- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Health check path: `/api/health`
- Environment: `ENABLE_SEMANTIC_SIMILARITY=false` for the existing TF-IDF mode.

The start command above is a Render/Linux command, not a PowerShell command.

## Verify

1. Open https://vidya-chaya-audit.onrender.com/api/health and wait for
   `{"status":"ok"}`.
2. Open the Vercel analysis page and upload a healthcare TXT document with
   at least 20 words.
3. Verify that Analysis History loads, and that the analysis produces results.

The frontend now waits for healthy JSON for up to two minutes before sending
requests, and bounds analysis requests to three minutes. Only health checks
retry; file submissions are sent once to avoid duplicate reports.
The analysis endpoint runs in a worker thread so health checks remain responsive.
Unexpected backend exceptions are logged and returned as readable JSON with
CORS headers. These changes do not repair a Render service that cannot start;
that still requires resolving the actual startup error in Render logs.
