# ⚡ PIVOT | AI-Powered Business Intelligence Platform

> **Local-First, Metadata-Driven Business Intelligence, Automated Data Profiling, Versioned Data Cleaning, and Grounded RAG AI Analytics.**

![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)
![FastAPI](https://img.shields.io/badge/Framework-FastAPI-green.svg)
![React](https://img.shields.io/badge/Frontend-React%20%2B%20Vite-61dafb.svg)
![Recharts](https://img.shields.io/badge/Library-Recharts-red.svg)
![Database](https://img.shields.io/badge/Database-SQLite%20%2F%20PostgreSQL-blue.svg)
![AI](https://img.shields.io/badge/AI-Google%20Gemini%20RAG-orange.svg)
![License](https://img.shields.io/badge/License-MIT-success.svg)

---

## 📌 Executive Overview

**Pivot** is an advanced, local-first Business Intelligence (BI) and Data Operations platform designed to help business leaders, analysts, and data scientists explore, clean, profile, and analyze complex datasets without writing repetitive boilerplate code.

Unlike traditional dashboards or cloud-only SaaS tools that overwrite source files or return ungrounded AI guesses, **Pivot gives every business dataset a memory**:
- **Source Preservation**: Uploaded files (**CSV**, **Excel**, **JSON**, **Parquet**) are stored as immutable **Version 0 (Source of Truth)**.
- **Traceable Version Lineage**: Every data transformation creates a new, distinct dataset version node, making all changes 100% reproducible and auditable.
- **Grounded RAG AI Analyst**: Answers questions using local dataset metadata and indexed business context documents (PDFs, glossaries), eliminating AI hallucinations.

---

## 🎯 Key Features & Capabilities

```
┌───────────────────┐     ┌───────────────────┐     ┌─────────────────────┐
│ 1. Ingestion &    │ ──> │ 2. Quality Engine │ ──> │ 3. Deterministic    │
│    Auto Profiling │     │    & Diagnostics  │     │    Data Cleaning    │
└───────────────────┘     └───────────────────┘     └─────────────────────┘
                                                               │
                                                               ▼
┌───────────────────┐     ┌───────────────────┐     ┌─────────────────────┐
│ 6. Versioned      │ <── │ 5. Read-Only SQL  │ <── │ 4. Grounded RAG     │
│    Lineage Node   │     │    Guard & Engine │     │    AI Analyst Chat  │
└───────────────────┘     └───────────────────┘     └─────────────────────┘
```

### ⚡ 1. Auto Pilot & Executive Briefings
- **One-Click Dataset Profiling**: In a single action, Auto Pilot scans numerical distributions, time series trends, dimensional correlations, and quality risks.
- **Deterministic Schema Planning**: Combines local statistical profiling with compact LLM planning (`GEMINI_API_KEY`) to select top KPIs, trends, and risk indicators.
- **Downloadable Executive Reports**: Automatically generates downloadable **Markdown**, **CSV**, and **PDF** briefings for executive decision-makers.

---

### 📂 2. Data Ingestion & Automated Profiling
- **Format Flexibility**: Ingest **CSV**, **Excel (.xlsx, .xls)**, **JSON**, and **Parquet** files up to 50MB.
- **Semantic Role Inference**: Automatically detects column data types, currency fields, time dimensions, primary-key candidates, and PII flags.
- **Transparent Quality Scoring**: Uses a deterministic, penalty-based scoring formula to calculate completeness, consistency, and uniqueness scores.

---

### 🧹 3. Deterministic Data Cleaning & Version Control
Preview and apply 7 core data transformations:
1. **Trim Whitespace**: Cleans leading and trailing string padding.
2. **Remove Duplicates**: Drops exact row-level duplicate entries.
3. **Normalize Headers**: Converts messy column names into clean `snake_case`.
4. **Parse & Standardize Dates**: Converts multi-format date strings into standard `YYYY-MM-DD`.
5. **Fill Missing Values**: Imputes missing numerical values with median and categoricals with mode.
6. **Remove Outliers**: Excludes statistical anomalies exceeding $1.5 \times \text{IQR}$.
7. **Combined Standardization**: Executes a complete multi-step cleaning pipeline.

> 🔒 **Lineage Guarantee**: Original raw files are *never modified*. Every approved transformation outputs a new versioned file registered in the SQLite metadata catalog (`data/pivot.db`).

---

### 🤖 4. AI Analyst & Grounded RAG Chat
- **Retrieval-Augmented Generation (RAG)**: Indexes dataset schemas, column profiles, sample rows, and custom business glossaries (PDF, JSON, Markdown).
- **Context-Grounded Answers**: Retrieves the most relevant dataset chunks via TF-IDF search before calling Gemini, citing exact column sources and avoiding hallucinations.
- **Interactive Recharts Generation**: Returns dynamically rendered bar charts, line trends, and key metrics directly in the chat window.

---

### 🗄️ 5. Read-Only SQL Workspace
- **Direct Query Console**: Run raw SQL queries against uploaded datasets in real time.
- **AST Safety Guard (`security.py`)**: Strict query validation allows only read-only statements (`SELECT`, `WITH` CTEs) while blocking unsafe DDL/DML operations (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`).

---

### 📈 6. Predictive Analytics & Scenario Simulator
- **Linear Regression Forecasting**: Predicts future metric trends with residual-based confidence bands.
- **Financial Scenario Modeling**: Simulates business impacts from custom price adjustments, marketing spend changes, and supplier cost variations.

---

## 📸 Visual Tour & User Interface

| Executive Dashboard & Auto Pilot | Data Quality Profiling & Issues |
| :---: | :---: |
| ![Dashboard Overview](<images/Screenshot 2026-07-30 152458.png>) | ![Quality Profiling](<images/Screenshot 2026-07-30 153435.png>) |

| Data Cleaning & Row Preview | Grounded AI Analyst Chat |
| :---: | :---: |
| ![Data Cleaning](<images/Screenshot 2026-07-30 160400.png>) | ![AI Analyst Chat](<images/Screenshot 2026-07-30 161908.png>) |

| SQL Workspace & Read-Only Guard | Version History & Lineage Node |
| :---: | :---: |
| ![SQL Console](<images/Screenshot 2026-07-30 162005.png>) | ![Version Lineage](<images/Screenshot 2026-07-30 160928.png>) |

| Financial Scenario Simulator | Time-Series Forecasting |
| :---: | :---: |
| ![Scenario Simulator](<images/Screenshot 2026-07-30 162233.png>) | ![Forecasting](<images/Screenshot 2026-07-30 162350.png>) |

---

## 🏗️ Architecture & Codebase Map

```text
d:\RPI Engine\
├── backend/
│   ├── app/
│   │   ├── main.py           # FastAPI entrypoint, HTTP routers, multi-step AI Agent
│   │   ├── assistant.py      # Analyst Calculation Engine & deterministic aggregations
│   │   ├── analytics.py      # Statistical profiling, linear forecasting & scenario models
│   │   ├── pipeline.py       # Deterministic data cleaning & versioned transformations
│   │   ├── rag.py            # RAG chunking, indexing & TF-IDF retrieval engine
│   │   ├── security.py       # AST SQL read-only safety validator
│   │   ├── store.py          # SQLite persistence for datasets, versions, & events
│   │   ├── config.py         # App configuration & Gemini settings
│   │   └── models.py         # Pydantic validation schemas
│   ├── data/
│   │   ├── files/            # Versioned dataset storage (.csv, .parquet)
│   │   └── pivot.db          # Metadata SQLite database
│   └── requirements.txt      # Python dependencies
├── src/
│   ├── AppPolished.jsx       # Core React frontend state controller & viewport manager
│   ├── main.jsx              # React mounting root
│   ├── styles.css            # Dashboard dark/light styling theme
│   └── utils.js              # Fetch wrappers & storage helpers
├── Dockerfile                # Backend & frontend single-container build
├── docker-compose.yml        # Docker compose service definition
└── package.json              # Frontend dependencies & scripts
```

---

## 💻 Tech Stack

- **Frontend**: React 18, Vite, Recharts, Lucide Icons, Tailwind-inspired CSS styling.
- **Backend API**: Python 3.10+, FastAPI, Uvicorn.
- **Data Engine**: Pandas, NumPy, Scikit-learn (IsolationForest outliers & linear regression).
- **Database & Persistence**: SQLite (`pivot.db`), SQLAlchemy, Alembic migrations.
- **AI & RAG Engine**: Google Gemini API (Runtime), TF-IDF Scikit-learn Vectorizer, custom chunking.

---

## 🛠️ Getting Started

### Prerequisites
- Python 3.10 or higher
- Node.js 18+ and `npm`

---

### Option A: Local Development Setup

#### 1. Backend Setup
```bash
# Navigate to project root
cd "d:\RPI Engine"

# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate       # Windows
# source .venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r backend/requirements.txt

# Start FastAPI server
python -m uvicorn backend.app.main:app --reload --port 8000
```
- **API Documentation**: [http://localhost:8000/docs](http://localhost:8000/docs)

#### 2. Frontend Setup
```bash
# In a new terminal window
cd "d:\RPI Engine"

# Install frontend dependencies
npm install

# Start Vite dev server
npm run dev
```
- **Web Dashboard**: [http://localhost:5173](http://localhost:5173)

---

### Option B: Docker Deployment

Run the complete full-stack environment in Docker:

```bash
docker-compose up --build
```

---

## 🔑 Environment Variables Configuration

Create a `backend/.env` file:

```env
# Optional Gemini API Key for AI Analyst & Auto Pilot reasoning
GEMINI_API_KEY=your_google_gemini_api_key

# Database Connection (Defaults to SQLite data/pivot.db)
DATABASE_URL=sqlite:///data/pivot.db
```

> ℹ️ *Note: If `GEMINI_API_KEY` is not provided, Pivot will complete all local profiling, data cleaning, quality scoring, SQL queries, and forecasting deterministically!*

---

## 🛡️ Security, Privacy & Integrity Guarantees

1. **Immutable Source Files**: Raw uploaded datasets (Version 0) are saved as read-only files on disk and can never be overwritten by API operations.
2. **Read-Only SQL Protection**: SQL query parser blocks any `UPDATE`, `DELETE`, `INSERT`, `ALTER`, `DROP`, or `PRAGMA` command to prevent database tampering.
3. **Deterministic Quality Metrics**: Dataset quality scores are computed using transparent statistical rules—never arbitrary or non-reproducible numbers.
4. **Context-Bounded AI RAG**: AI answers are strictly bounded to retrieved chunks of your dataset and business glossaries, citing sources to eliminate hallucinations.

---

## 🚀 Roadmap & Future Enhancements

- [ ] **PostgreSQL & MinIO Storage**: Replace SQLite and local files with PostgreSQL and S3/MinIO object storage for cloud scale.
- [ ] **Enterprise RBAC & Authentication**: Add Google OAuth, user roles, workspace permissions, and audit logs.
- [ ] **Database Connectors**: Direct connectors for PostgreSQL, MySQL, Snowflake, BigQuery, and DuckDB.
- [ ] **Background Job Queues**: Redis + Celery/RQ for handling multi-gigabyte dataset ingestion and asynchronous jobs.

---

## 📜 License

Distributed under the **MIT License**. See `LICENSE` for more information.

---
*Built with ❤️ for data-driven teams who want fast, reliable, and trustworthy business intelligence.*
