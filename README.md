# Pivot

> AI-powered Business Intelligence platform for exploring, cleaning, and analyzing datasets.

Pivot is an AI-powered Business Intelligence platform that helps users understand their data without writing repetitive code.

Upload a **CSV** or **Excel** file, and Pivot automatically profiles the dataset, detects quality issues, generates insights, and lets you explore the data using natural language or SQL.

Instead of modifying the uploaded dataset, Pivot preserves the original file and creates new versions whenever transformations are applied, making every change traceable and reproducible.

---

## Features

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
- SQLite

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

Add your Gemini API key (optional):

```env
GEMINI_API_KEY=your_api_key
```

---

## Roadmap

- Authentication & user accounts
- Multi-user workspaces
- Interactive dashboards
- Advanced lineage visualization
- Database connectors
- Scheduled reports
- Workflow automation
- Cloud storage support
- Enterprise RBAC

---

## Built With

- React
- FastAPI
- Pandas
- SQLite
- Scikit-learn
- Gemini API

---

## License

MIT License.
