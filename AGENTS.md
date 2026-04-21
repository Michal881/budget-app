# AGENTS.md

## What this project is
This is a simple **Budget App**:
- Backend: **FastAPI** (`main.py`)
- Frontend: single-page **HTML + JavaScript** (`index.html`)
- Data: SQLite (`budget.db`) plus JSON settings (`data.json`)

## Run locally (backend)
1. Create and activate a virtual environment.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Start FastAPI:
   ```bash
   uvicorn main:app --reload
   ```
4. Backend will be available at `http://127.0.0.1:8000`.

## How frontend connects to backend
- Frontend API base URL is resolved in `index.html` and can be overridden in `config.js` via `window.BUDGET_APP_CONFIG.apiBaseUrl`.
- Local default: when frontend runs on `localhost`/`127.0.0.1`, it calls `http://127.0.0.1:8000`.
- Production: set `apiBaseUrl` in `config.js` to your backend URL (for example, Render backend URL).

## Deploy on Render (simple setup)
- **Backend service**: create a Render Web Service from this repo.
  - Build command: `pip install -r requirements.txt`
  - Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- **Frontend**:
  - Easiest option: serve `index.html` from the same FastAPI service (`/` route already does this).
  - If hosting frontend separately, set `config.js -> apiBaseUrl` to the backend Render URL.

## Basic testing checklist
- [ ] Run backend and open `http://127.0.0.1:8000/health` (should return `{"status":"ok"}`).
- [ ] Open app in browser and add an expense.
- [ ] Confirm expense appears in list/summary.
- [ ] Add and delete a category.
- [ ] Verify no CORS/API errors in browser console.
