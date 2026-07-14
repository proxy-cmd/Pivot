# Pivot

> **Business Intelligence with Memory**

Pivot is an AI-powered Data Intelligence Platform that transforms raw structured data into explainable, reproducible business insights. Instead of acting as another dashboard or chatbot, Pivot understands datasets, builds semantic knowledge, detects quality issues, records every transformation, and helps users analyze data using natural language, SQL, and deterministic analytical pipelines.

The goal is simple: eliminate repetitive analytical work while keeping every decision transparent, traceable, and under the user's control.

---

# Core Philosophy

Pivot follows one principle:

> **The uploaded dataset becomes the center of the entire workspace.**

The original file is never modified.

Instead, Pivot creates an intelligent workspace around it by generating metadata, profiling statistics, semantic understanding, quality reports, lineage, version history, retrieval indexes, and AI context.

Every page inside the application is generated from the active dataset—not from hardcoded dashboards or placeholder content.

---

# Current Capabilities

## Dataset Management

- Upload CSV, Excel, JSON and Parquet datasets.
- Preserve original files as immutable source-of-truth.
- Create isolated dataset workspaces.
- Automatic schema discovery.
- Dataset fingerprinting.
- Version-aware processing.

---

## Intelligent Profiling

Automatically detects:

- Column data types
- Date fields
- Numeric measures
- Monetary values
- Candidate primary keys
- Candidate foreign keys
- Missing values
- Unique counts
- Business entities
- Semantic meaning
- Confidence scores
- Column statistics

---

## Data Quality Engine

Automatically identifies:

- Missing values
- Duplicate records
- Invalid dates
- Mixed data formats
- Outliers
- Negative values
- Whitespace issues
- Inconsistent categories
- Encoding problems
- Potential data quality risks

Each issue includes severity, explanation, business impact, and suggested fixes.

---

## Metadata & Lineage

Every dataset maintains:

- Metadata profile
- Event history
- Version history
- Transformation lineage
- Dataset fingerprints
- Processing logs

Nothing is modified automatically.

Every transformation requires approval and remains fully traceable.

---

## Safe Transformations

Current transformation pipeline supports:

- Trim text
- Remove duplicates
- Normalize names
- Parse dates

Approved transformations create new dataset versions while preserving the original source.

---

## AI Analyst

Pivot integrates Retrieval-Augmented Generation (RAG) instead of allowing unrestricted LLM access.

The AI:

- Retrieves dataset metadata
- Retrieves relevant document chunks
- Uses TF-IDF retrieval
- Grounds every answer in available evidence
- Supports Gemini (optional)

The language model never interacts directly with raw datasets without retrieval and validation.

---

## SQL Workspace

Pivot includes a secure SQL execution layer.

Supported:

- Read-only `SELECT`
- Common Table Expressions (`WITH`)

Blocked:

- INSERT
- UPDATE
- DELETE
- DROP
- ALTER
- CREATE
- Multi-statement execution

---

## Analytics

Current analytical capabilities include:

- KPI summaries
- Business health scoring
- Trend analysis
- Forecasting
- Confidence intervals
- Scenario simulation
- Anomaly detection

---

## Live Experience

The application supports:

- Live analysis events
- Streaming AI responses
- Dataset-aware workspace
- Real-time progress updates

---

# Technology Stack

## Frontend

- React
- TypeScript
- Tailwind CSS
- Vite

---

## Backend

- FastAPI
- Pandas
- NumPy
- Scikit-learn
- SQLite

---

## AI

- Google Gemini (optional)
- TF-IDF Retrieval
- Retrieval-Augmented Generation (RAG)

---

# Architecture

```text
                     User Upload
                          │
                          ▼
                 Dataset Workspace
                          │
      ┌───────────────────┼───────────────────┐
      ▼                   ▼                   ▼
 Metadata Engine    Quality Engine      SQLite Store
      │                   │                   │
      └──────────────┬────┴───────────────────┘
                     ▼
             Semantic Understanding
                     │
      ┌──────────────┼────────────────┐
      ▼              ▼                ▼
  AI Analyst     SQL Engine      Analytics
      │              │                │
      └──────────────┼────────────────┘
                     ▼
              Reports & Insights
```

---

# Running Locally

## Backend

```powershell
python -m venv .venv

.\.venv\Scripts\Activate.ps1

pip install -r backend/requirements.txt

Copy-Item backend/.env.example backend/.env

python -m uvicorn backend.app.main:app --reload
```

---

## Frontend

```powershell
npm install

npm run dev
```

Frontend:

```
http://localhost:5173
```

Backend API:

```
http://localhost:8000/docs
```

---

## Sample Dataset

For demonstration purposes:

```
sample-data/retail-orders.csv
```

This dataset showcases:

- Sales
- Customers
- Products
- Regions
- Shipping
- Semantic profiling
- Quality analysis
- AI querying

---

## Gemini Configuration

Create:

```
backend/.env
```

Add:

```env
GEMINI_API_KEY=your_api_key
```

The API key is used only on the backend.

Never expose it to the frontend.

---

# Testing

Run backend tests:

```powershell
pytest backend/tests
```

GitHub Actions automatically executes:

- Backend tests
- Production web build

for every push and pull request.

---

# Roadmap

Upcoming work includes:

- Dynamic dataset-driven dashboards
- AI-generated analytical workflows
- Interactive Cleaning Studio
- Version comparison
- Advanced lineage graph
- Report builder
- Natural-language SQL
- Multi-user workspaces
- Scheduled reports
- Database connectors
- Cloud storage integrations
- Vector database support
- Enterprise authentication
- Role-based access control
- Audit logs
- Background workers
- Workflow automation

---

# Vision

Pivot is not another dashboard.

It is a Business Intelligence Platform that understands data before analyzing it.

Every uploaded dataset becomes an intelligent workspace with memory, semantic understanding, explainable AI, reproducible transformations, and traceable decision-making—allowing users to spend less time preparing data and more time making decisions.