# Restaurant Recommender (MVP)

Geoapify‑powered restaurant recommendation service using HelloAgents patterns.

- Endpoints: `GET /healthz`, `GET /health/geo`, `GET /health/llm`, `POST /recommend`, and static `/` test page
- Flow: parse preferences (LLM with rules fallback) → geocode → bbox → Geoapify rect → dedupe → rank → Markdown report

## Run (macOS one‑shot)

```
bash scripts/start_all_mac.sh
```

This script:
- Loads `.env` (Geoapify key)
- Ensures Homebrew + Ollama, starts ollama, pulls `llama3.2`
- Creates venv, installs deps, starts FastAPI on `http://localhost:8010/`
- Opens the browser with the built‑in test page

If `pip install -e .` fails (no packaging), it will fallback to `pip install -r requirements.txt`.

## Dev quick start (backend + frontend)

From the standalone project root (`restaurant-recommender/`) you can start both services with:

```
bash scripts/start_dev.sh
```

The script will:
- Ensure the backend virtualenv exists, load `.env`, and start uvicorn on port 8010
- Install frontend dependencies if necessary, prefer Homebrew `node@20`, and run Vite on port 5173
- Store logs under `.logs/` and process IDs under `.pids/`

Stop both services with:

```
kill $(cat .pids/backend.pid) $(cat .pids/frontend.pid)
```

## Evaluation

Run the US-focused evaluation set (backend must be running locally):

```
python eval/run_eval.py --base http://localhost:8010 --k 5 --timeout 60 --queries eval/queries_us.jsonl --judgments eval/judgments_us.jsonl --out eval/report_us
```

The script writes `metrics.csv`, `report.md`, and optionally `errors.jsonl`. Use `--baseline path/to/metrics.csv` to compare against a previous run.

## Env
- `GEOAPIFY_API_KEY` (required)
- Optional LLM: `LLM_PROVIDER=ollama`, `LOCAL_LLM=llama3.2`, `OLLAMA_BASE_URL=http://localhost:11434`
- Reranker (optional): `RERANK_ENABLED=true`, `RERANK_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2`, `RERANK_WEIGHT=0.4`, `RERANK_TOP_N=10`
