@echo off
echo ========================================================
echo Starting Vidya Chaya Audit (Local Mode)
echo ========================================================
cd /d "%~dp0"

echo [1/2] Starting FastAPI Backend on http://localhost:8000 ...
start "Vidya Chaya Backend" cmd /k "cd backend && python -m uvicorn app.main:app --reload --port 8000"

echo [2/2] Starting React/Vite Frontend ...
start "Vidya Chaya Frontend" cmd /k "cd frontend && npm run dev"

echo.
echo Both services are starting in separate windows.
echo Open http://localhost:5173 in your browser once the Vite server is ready.
echo ========================================================
