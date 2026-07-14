# Pivot — Business Intelligence with Memory

Pivot is a metadata-driven data engineering and analytics workspace. It is designed to remove repetitive analyst work without hiding decisions: it preserves the original source, understands the shape and meaning of data, flags quality risks, records every approved change, and lets people ask grounded questions about their data.

## What is working today

- **Dataset sessions:** CSV, Excel, JSON and Parquet uploads are stored unchanged as the source of truth.
- **Profiling and semantic hints:** column types, missing data, candidate keys, dates, numeric and money fields, and probable business role are inferred automatically.
- **Trust signals:** dataset fingerprints, PII flags, whitespace checks and per-column semantic confidence/evidence are captured alongside the profile.
- **Quality engine:** missing values, duplicates, invalid dates, suspicious negative values and statistical outliers are identified with business impact and proposed fixes.
- **Metadata and lineage:** each dataset has a persistent profile, event history and versioned transformation plan. Nothing is changed automatically.
- **Safe transformation planning:** trim text, de-duplicate, normalize names and parse-date actions are recorded as approval-required lineage entries.
- **Reproducible execution:** approved deterministic transformations can produce a separate version output while keeping the original file unchanged.
- **SQL guardrail:** the API accepts only validated read-only `SELECT`/`WITH` SQL; all mutation, schema and multi-statement operations are rejected.
- **RAG assistant:** uploaded dataset samples and PDF/JSON document chunks are indexed locally with TF-IDF retrieval. The chat endpoint retrieves relevant context before answering. With Gemini configured, answers are generated from that retrieved context and include source citations.
- **Analytics:** business-health score, KPI trends, anomaly signals, forecasts with confidence bounds, and a scenario simulator powered by the Python API.
- **Live experience:** the UI shows a live grounded-chat state and the API exposes server-sent analysis events for real-time clients.

## Architecture

```text
React dashboard → FastAPI service → metadata / lineage SQLite store
                              ├─ profiling + quality engine (Pandas, scikit-learn)
                              ├─ forecasting + scenario analysis
                              ├─ local retrieval index (TF-IDF)
                              └─ Gemini (optional, server-side only)
```

The AI is deliberately not allowed to edit raw files, invent figures, or bypass the metadata layer. It receives dashboard facts and retrieved source context, while the deterministic backend handles profiling, validation and lineage.

## Run locally

Start the API:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
Copy-Item backend/.env.example backend/.env
python -m uvicorn backend.app.main:app --reload --port 8000
```

Start the dashboard in a second terminal:

```powershell
npm install
npm run dev
```

Open `http://localhost:5173`. API documentation is available at `http://localhost:8000/docs`.

For fast demo, upload [`sample-data/retail-orders.csv`](sample-data/retail-orders.csv). It contains sales, customer, product, region and shipping fields so Pivot can demonstrate semantic profiling, quality checks and grounded chat immediately.

To enable grounded Gemini answers, set `GEMINI_API_KEY` in `backend/.env`. Never put a key in a `VITE_` variable: browser environment values are public.

## Deploy

```powershell
Copy-Item backend/.env.example backend/.env
docker compose up --build
```

This creates one production container on port 8000. In a real deployment, use managed object storage for source files, PostgreSQL for metadata, a managed vector database for large-scale retrieval, user authentication/roles, encrypted secrets, audit retention, background workers and a TLS reverse proxy.

## Product direction

Pivot is intentionally built in layers: deterministic data engineering first, metadata and lineage next, then retrieval-grounded AI orchestration. That makes it a credible foundation for safe natural-language analysis, source connectors, validated read-only SQL, reusable workflows, scheduled reports, and multi-user collaboration—not another disposable dashboard.

## Verification

The repository includes focused tests for forecasting intervals, scenario directionality, local retrieval and SQL safety. Run them with:

```powershell
pytest backend/tests
```

GitHub Actions runs the Python tests and production web build on every push and pull request.
