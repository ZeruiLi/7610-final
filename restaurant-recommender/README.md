# TastyGo (Standalone Build)

Geoapify-powered restaurant recommendation service with a FastAPI backend, React/Vite frontend, and evaluation scripts. The backend parses natural-language dining requests, searches Geoapify for candidates, ranks/reranks them, enriches the top picks with detail sources, and returns both structured cards and an explanatory Markdown report. The frontend provides a conversational interface, result cards, Markdown rendering, and preference diagnostics.

## Project Layout
```
restaurant-recommender/
├── backend/              # FastAPI app + services
├── frontend/             # Vite/React UI for the TastyGo experience
├── eval/                 # JSONL datasets + evaluation runner
├── scripts/              # helper scripts (dev launcher, etc.)
├── README.md             # this file
└── ...
```

## Requirements
- Python 3.10+ (tested on 3.11)
- Node.js 18+ (Node 20 recommended)
- npm (bundled with Node)
- Geoapify API key (required)
- Optional: Ollama or any OpenAI-compatible endpoint for preference parsing/reranking (falls back to heuristic mode if omitted)

## Environment Variables
Create `backend/.env` based on `backend/.env.example` (do **not** commit the .env file):
```
GEOAPIFY_API_KEY=sk-xxxx                    # required
LLM_PROVIDER=ollama                         # optional
LOCAL_LLM=llama3.2                          # optional
OLLAMA_BASE_URL=http://localhost:11434      # optional
# ...see backend/.env.example for more knobs
```
Frontend requests assume the backend runs on `http://localhost:8010`. Override by creating `frontend/.env.local` with `VITE_API_BASE=<url>`.

## Quick Start
From the `restaurant-recommender/` directory:
```
bash scripts/start_dev.sh
```
This script now serves as a one-click **restart**:
1. Stops any previously running backend/frontend instances (kills stored PIDs and frees ports 8010/5173).
2. Creates/updates `backend/.venv`, installs Python deps, loads `backend/.env` and starts FastAPI on port 8010.
3. Installs frontend npm deps (if needed) and runs `npm run dev` on port 5173.
4. Logs go to `.logs/`, process ids to `.pids/`.

Stop both services with:
```
kill $(cat .pids/backend.pid) $(cat .pids/frontend.pid)
```

## Manual Backend Run
```
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # edit with your key
cd src
uvicorn main:app --reload --port 8010
```

## Manual Frontend Run
```
cd frontend
npm install
npm run dev -- --port 5173
```
Visit http://localhost:5173/ (frontend) which proxies requests to http://localhost:8010/recommend.

## Evaluation
Run the offline evaluator while the backend is serving on localhost:
```
cd restaurant-recommender
python eval/run_eval.py \
  --base http://localhost:8010 \
  --k 5 --timeout 60 \
  --queries eval/queries_us.jsonl \
  --judgments eval/judgments_us.jsonl \
  --out eval/report_us
```
Outputs `metrics.csv`, `report.md`, and `errors.jsonl` for debugging.

## Testing
```
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest
```

## Notes
- `frontend/README.md` and `backend/README.md` include more detailed component/service descriptions.
- Flutter Web assets under `backend/src/static/app` are optional; remove them if you prefer a React-only deployment.
- Never commit `.env`, API keys, or `.logs/.pids`. Root `.gitignore` already guards against this.

## Session Memory & New Chats
- Both `/recommend` and `/recommend-stream` accept an optional `session_id`. When supplied, the backend keeps a short rolling history so the preference parser can see the last few turns.
- Trigger `POST /session/reset` with `{ "session_id": "<id>" }` (already wired to the frontend “New Chat” button) to clear previous turns and start a fresh conversation.
