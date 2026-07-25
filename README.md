# Pivot

> AI-powered Business Intelligence platform for exploring, cleaning, and analyzing datasets.

Pivot is an AI-powered Business Intelligence platform that helps users understand their data without writing repetitive code.

Upload a **CSV**, **Excel**, **JSON**, or **Parquet** file, and Pivot automatically profiles the dataset, detects quality issues, generates insights, and lets you explore the data using natural language or SQL.

Instead of modifying the uploaded dataset, Pivot preserves the original file and creates new versions whenever transformations are applied, making every change traceable and reproducible.

---

## Features

### Auto Pilot

Auto Pilot turns a new dataset into a complete first-pass briefing with one action.

It first runs a safe local analysis across usable numeric fields, dimensions, time series, distributions, correlations, and quality risks. When `GEMINI_API_KEY` is configured, it makes one compact planning call using this calculated schema context to select the most useful analysis focus, KPIs, charts, and next checks. Pivot validates every selected field and calculates every displayed number locally.

Each run:

- Standardizes safe formats, removes exact duplicates, and normalizes headers
- Creates and activates a traceable cleaned dataset version
- Preserves the original upload unchanged
- Produces KPI cards, trends, comparisons, distributions, findings, and analysis coverage
- Creates a downloadable Markdown executive briefing

Auto Pilot does not automatically fill missing values or remove outliers because those changes need business review. Without a Gemini key, it still completes the local investigation and uses the detected dataset structure as its plan.

---

### 📂 Upload & Profile

- Upload CSV and Excel datasets
- Automatic schema detection
- Column profiling
- Missing value analysis
- Duplicate detection
- Statistical summaries
- Dataset overview

---

### 🧹 Data Cleaning

Preview and apply common cleaning operations.

Current transformations include:

- Trim whitespace
- Remove duplicates
- Parse dates
- Fill missing values
- Normalize text
- Detect outliers

Every transformation creates a new dataset version while keeping the original file unchanged.

---

### 🤖 AI Analyst

Pivot includes an AI-powered chatbot that understands your dataset using a **Retrieval-Augmented Generation (RAG)** pipeline.

Instead of answering from general knowledge, Pivot retrieves the most relevant dataset context before generating a response, making answers grounded in your uploaded data.

You can ask questions like:

> Which region generated the highest revenue?

> Show monthly sales trends.

> Which products are underperforming?

> Find duplicate customer records.

> Fill missing values and generate a cleaned dataset.

> Explain why sales dropped in March.

Depending on the request, Pivot can:

- Answer questions about the dataset
- Generate charts and summaries
- Identify trends and anomalies
- Compare metrics across categories
- Detect data quality issues
- Suggest and apply data cleaning operations
- Create new dataset versions
- Generate read-only SQL queries
- Explain how results were calculated

When deterministic analysis isn't sufficient, Gemini can be used as an optional fallback while remaining grounded through the RAG retrieval pipeline.

---

### 🧠 Retrieval-Augmented Generation (RAG)

For every uploaded dataset, Pivot builds a searchable knowledge base using dataset metadata, profiling information, and processed content.

When a question is asked, the system:

1. Retrieves the most relevant dataset context.
2. Combines it with metadata and profiling information.
3. Sends only the relevant context to the AI model.
4. Generates a grounded response based on the retrieved data.

This approach reduces hallucinations and keeps responses focused on the uploaded dataset rather than relying on general knowledge.

### Business context

Attach a PDF, Markdown, text, or JSON business glossary from the AI Analyst. Pivot indexes the readable content in the dataset's private context, so questions can use definitions such as how your company defines an active customer or revenue.

### Private workspaces

- Google OAuth sign-in with short-lived access tokens and rotated refresh sessions
- Dataset, report, version, transformation, event, and RAG-context ownership enforced on every API request
- PostgreSQL-ready SQLAlchemy persistence with Alembic migrations

---

### 📊 Analytics

Generate:

- KPI summaries
- Trend analysis
- Rankings
- Correlation analysis
- Forecasting
- Business Health Score
- Scenario Analysis
- Anomaly Detection

---

### 🗄 SQL Workspace

Run SQL directly on the uploaded dataset.

Supported:

- `SELECT`
- `WITH` (CTEs)

Blocked:

- `INSERT`
- `UPDATE`
- `DELETE`
- `DROP`
- `ALTER`
- `CREATE`

---

### 📝 Version History

Every approved transformation creates a new dataset version.

Track every modification while preserving the original uploaded file.

---

## Tech Stack

### Frontend

- React
- Vite
- Recharts

### Backend

- FastAPI
- Pandas
- NumPy
- Scikit-learn
- PostgreSQL (production) / SQLite (tests)

### AI

- Google Gemini API (Runtime)
- OpenAI GPT-5.5 & GPT-5.6 (Luna & Terra) for development, debugging, code review, and implementation assistance
- TF-IDF Retrieval
- Retrieval-Augmented Generation (RAG)

---

## Project Structure

```text
frontend/
backend/
sample-data/
```

---

## Getting Started

### Backend

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

pip install -r backend/requirements.txt

python -m uvicorn backend.app.main:app --reload
```

### Frontend

```bash
npm install

npm run dev
```

Frontend

```
http://localhost:5173
```

Backend API

```
http://localhost:8000/docs
```

---

## Environment Variables

Create:

```
backend/.env
```

Configure the database, Google OAuth, and optional Gemini key. Use [the setup guide](docs/SETUP.md) for local and Docker setup.

```env
GEMINI_API_KEY=your_api_key
```

## Current limits

Pivot uses Pandas for in-process profiling and analysis. The default upload limit is 50MB, which keeps a single API process responsive and avoids pretending that arbitrary-size files are safe on a laptop. For larger sources, the next production step is object storage plus a worker queue and a query engine such as DuckDB or warehouse connectors.

---

## Roadmap

- Interactive dashboards
- Advanced lineage visualization
- Database connectors
- Scheduled reports
- Scheduled workflow automation
- Cloud storage support
- Enterprise RBAC

---

## Built With

- React
- FastAPI
- Pandas
- PostgreSQL
- Scikit-learn
- Gemini API

---

## License

MIT License.
