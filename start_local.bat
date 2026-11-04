@echo off
echo ========================================================
echo Starting Vidya Chaya Audit (Local Mode)
echo VTU Plagiarism Detector - Biomedical AI Research
echo ========================================================
cd /d "%~dp0"

echo [1/2] Starting FastAPI Backend on http://localhost:8001 ...
start "Vidya Chaya Backend" cmd /k "cd backend && python -m uvicorn app.main:app --reload --port 8001"

echo [2/2] Starting React/Vite Frontend on http://localhost:5173 ...
start "Vidya Chaya Frontend" cmd /k "cd frontend && npm run dev"

echo.
echo Both services are starting in separate windows.
echo - Backend:  http://127.0.0.1:8001
echo - Frontend: http://localhost:5173
echo.
echo ONLINE ACADEMIC INTEGRITY ANALYSIS:
echo Retrieves relevant peer-reviewed academic papers dynamically
echo from global repositories via CORE API using configured credentials.
echo ========================================================
