from __future__ import annotations

import asyncio
import io
import json
import re
from uuid import uuid4
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .analytics import _numeric_series, forecast, prepare_frame, profile_frame, scenario
from .config import get_settings
from .models import AnalysisRequest, ChatRequest, ReportRequest, ScenarioRequest, SqlAskRequest, SqlRequest, TransformRequest
from .pipeline import apply
from .rag import extract, retrieve
from .security import validate_readonly_sql
from .store import (
    FILES, add_chunks, add_report, add_version, chunks_for, create_dataset, create_transformation,
    events_for, finish_dataset, get_dataset, get_transformation, reports_for, resolve_transformation, activate_dataset_version,
)

app = FastAPI(title='Pivot Analytics API', version='1.1.0')
settings = get_settings()
cors_origins = sorted({origin.strip() for origin in settings.cors_origins.split(',') if origin.strip()} | {'http://localhost:5173', 'http://127.0.0.1:5173'})
app.add_middleware(CORSMiddleware, allow_origins=cors_origins, allow_credentials=True, allow_methods=['GET', 'POST', 'OPTIONS'], allow_headers=['Content-Type', 'Authorization'])

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
ALLOWED_SUFFIXES = {'.csv', '.xlsx', '.xls', '.json', '.parquet'}
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _absolute_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _dataset_or_404(dataset_id: str) -> dict:
    item = get_dataset(dataset_id)
    if not item:
        raise HTTPException(404, 'Dataset session not found.')
    return item


def _read_bytes(raw: bytes, suffix: str) -> pd.DataFrame:
    source = io.BytesIO(raw)
    if suffix in ('.xlsx', '.xls'):
        return pd.read_excel(source)
    if suffix == '.json':
        return pd.read_json(source)
    if suffix == '.parquet':
        return pd.read_parquet(source)
    return pd.read_csv(source)


def _read_source(item: dict) -> pd.DataFrame:
    path = _absolute_path(item.get('active_path') or item['source_path'])
    if not path.exists():
        raise HTTPException(404, 'The preserved source file is unavailable.')
    suffix = path.suffix.lower()
    try:
        if suffix in ('.xlsx', '.xls'):
            frame = pd.read_excel(path)
        elif suffix == '.json':
            frame = pd.read_json(path)
        elif suffix == '.parquet':
            frame = pd.read_parquet(path)
        else:
            frame = pd.read_csv(path)
    except Exception as error:
        raise HTTPException(422, f'Could not read the preserved source: {error}') from error
    frame = prepare_frame(frame)
    profile = item.get('profile') or {}
    for column in profile.get('schema', {}).get('numeric_columns', []):
        if column in frame.columns:
            frame[column] = _numeric_series(frame, column)
    return frame


def _profile_payload(frame: pd.DataFrame, filename: str, dataset_id: str) -> dict[str, Any]:
    result = profile_frame(frame, filename)
    result['dataset_id'] = dataset_id
    result['preview'] = json.loads(frame.head(8).fillna('').to_json(orient='records', date_format='iso'))
    result['columns_list'] = [str(column) for column in frame.columns]
    issue_operations = {
        'missing_values': ('fill_missing', 'Fill missing values'),
        'duplicate_records': ('remove_duplicates', 'Remove exact duplicates'),
        'whitespace': ('trim_text', 'Trim text fields'),
        'invalid_dates': ('parse_dates', 'Parse detected date fields'),
        'outliers': ('remove_outliers', 'Review numeric outliers'),
    }
    recommendations = []
    for issue in result.get('issues', []):
        operation, label = issue_operations.get(issue['type'], ('normalize_columns', 'Normalize column names'))
        if not any(item['operation'] == operation for item in recommendations):
            recommendations.append({'operation': operation, 'label': label, 'reason': issue['fix']})
    result['recommendations'] = recommendations
    return result


def _overview(frame: pd.DataFrame, profile: dict) -> dict[str, Any]:
    schema = profile.get('schema', {})
    numeric = schema.get('numeric_columns', [])
    dates = schema.get('date_columns', [])
    cards = [
        {'label': 'Rows', 'value': profile.get('rows', 0), 'kind': 'count'},
        {'label': 'Columns', 'value': profile.get('columns', 0), 'kind': 'count'},
        {'label': 'Quality score', 'value': profile.get('quality_score', 0), 'suffix': '/100', 'kind': 'quality'},
    ]
    for column in numeric[:3]:
        values = _numeric_series(frame, column).dropna()
        if len(values):
            cards.append({'label': column.replace('_', ' ').title(), 'value': round(float(values.sum()), 2), 'kind': 'metric', 'column': column})
    chart: list[dict[str, Any]] = []
    if dates and numeric:
        date_column, value_column = dates[0], numeric[0]
        dates_series = pd.to_datetime(frame[date_column], errors='coerce')
        values = _numeric_series(frame, value_column)
        grouped = pd.DataFrame({'period': dates_series.dt.to_period('M').astype('string'), 'value': values}).dropna()
        if not grouped.empty:
            chart = [{'period': str(row['period']), 'value': round(float(row['value']), 2)} for _, row in grouped.groupby('period', as_index=False)['value'].sum().tail(24).iterrows()]
    breakdown = []
    dimensions = [column for column in frame.columns if column not in numeric and column not in dates]
    if dimensions:
        dimension = dimensions[0]
        counts = frame[dimension].fillna('(blank)').astype(str).value_counts().head(8)
        breakdown = [{'label': str(label), 'value': int(value)} for label, value in counts.items()]
    return {'cards': cards, 'trend': chart, 'breakdown': breakdown, 'trend_columns': {'date': dates[0] if dates else None, 'value': numeric[0] if numeric else None}}


def _analyses(frame: pd.DataFrame, profile: dict) -> list[dict[str, Any]]:
    schema = profile.get('schema', {})
    analyses = []
    for column in schema.get('numeric_columns', []):
        analyses.append({'id': f'trend:{column}', 'kind': 'trend', 'title': f'Trend of {column.replace("_", " ")}', 'description': f'Inspect how {column.replace("_", " ")} changes over time.', 'column': column, 'enabled': bool(schema.get('date_columns'))})
        analyses.append({'id': f'distribution:{column}', 'kind': 'distribution', 'title': f'Distribution of {column.replace("_", " ")}', 'description': f'Summarize the spread, center, and extremes of {column.replace("_", " ")}.', 'column': column, 'enabled': True})
    dimensions = [column for column in frame.columns if column not in schema.get('numeric_columns', []) and column not in schema.get('date_columns', [])]
    for column in dimensions[:8]:
        analyses.append({'id': f'breakdown:{column}', 'kind': 'breakdown', 'title': f'Breakdown by {column.replace("_", " ")}', 'description': f'Compare the most common values in {column.replace("_", " ")}.', 'column': column, 'enabled': True})
    analyses.append({'id': 'quality', 'kind': 'quality', 'title': 'Data quality review', 'description': 'Review completeness, duplicates, and detected quality risks.', 'enabled': True})
    return analyses


def _quote(value: str) -> str:
    return '"' + str(value).replace('"', '""') + '"'


def _execute_frame(frame: pd.DataFrame, query: str) -> dict[str, Any]:
    import sqlite3
    db = sqlite3.connect(':memory:')
    try:
        sql_frame = frame.copy()
        for column in sql_frame.select_dtypes(include=['object', 'string']).columns:
            if any(word in str(column).lower() for word in ('date', 'time', 'month', 'year')):
                parsed = pd.to_datetime(sql_frame[column], format='mixed', errors='coerce')
                if parsed.notna().mean() >= 0.2:
                    sql_frame[column] = parsed.dt.strftime('%Y-%m-%d')
        sql_frame.to_sql('dataset', db, index=False, if_exists='replace')
        result = pd.read_sql_query(query, db)
        return {'columns': result.columns.tolist(), 'rows': json.loads(result.head(200).fillna('').to_json(orient='records')), 'count': int(len(result))}
    finally:
        db.close()


def _analysis_summary(kind: str, column: str | None, result: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    rows = result.get('rows') or []
    schema = profile.get('schema', {})
    metric_name = column or (schema.get('numeric_columns') or ['value'])[0]
    if kind == 'trend' and rows:
        values = [float(row.get('value', 0) or 0) for row in rows]
        peak = rows[values.index(max(values))]
        low = rows[values.index(min(values))]
        return {'metric': metric_name, 'aggregation': 'monthly sum', 'periods': len(rows), 'total': round(sum(values), 2), 'average': round(sum(values) / len(values), 2), 'highest_period': {'period': peak.get('period') or peak.get('label'), 'value': round(max(values), 2)}, 'lowest_period': {'period': low.get('period') or low.get('label'), 'value': round(min(values), 2)}}
    if kind == 'distribution':
        metrics = result.get('metrics') or {}
        return {'metric': metric_name, 'aggregation': 'distribution', **metrics}
    if kind == 'breakdown' and rows:
        first = rows[0]
        label_key = 'dimension' if 'dimension' in first else 'label'
        value_key = 'value'
        return {'field': metric_name, 'aggregation': 'row count', 'groups': len(rows), 'top_group': {'value': first.get(label_key), 'count': first.get(value_key)}}
    return {}


def _chat_summary(question: str, item: dict, query_result: dict[str, Any], query: str | None) -> str:
    profile = item.get('profile') or {}
    rows = query_result.get('rows') or []
    lower = question.lower()
    if any(word in lower for word in ('who are you', 'what are you', 'your name', 'what can you do')):
        return f"I’m Pivot Analyst, your evidence-backed data analyst. I’m connected to {item['name']} with {profile.get('rows', 0):,} rows and {profile.get('columns', 0)} detected fields. I can investigate trends, highest values, quality issues, and group comparisons by running read-only evidence queries."
    if not rows:
        return f"I’m connected to {item['name']}, but I couldn’t find enough evidence for that question in the current source. Try naming a field such as {', '.join((profile.get('columns_list') or [])[:4])}."
    first = rows[0]
    if any(word in lower for word in ('highest', 'top', 'most', 'best')) and 'dimension' in first:
        return f"The highest grouped value is {first.get('dimension')} at {float(first.get('value', 0)):,.2f} for the selected metric. I grouped by the detected field and ordered the evidence descending."
    if ('trend' in lower or 'month' in lower or 'time' in lower) and 'period' in first:
        values = [float(row.get('value', 0) or 0) for row in rows]
        peak = rows[values.index(max(values))]
        return f"The {query_result.get('count', len(rows))}-period trend totals {sum(values):,.2f}, averaging {sum(values) / len(values):,.2f} per period. The highest period is {peak.get('period')} at {max(values):,.2f}."
    if 'value' in first and len(first) == 1:
        return f"The evidence result is {float(first['value']):,.2f}. This was calculated directly from the detected numeric field using a read-only query."
    fields = ', '.join(query_result.get('columns') or first.keys())
    return f"I found {query_result.get('count', len(rows)):,} evidence rows with fields {fields}. The first result is shown below so you can inspect the exact values returned by the query."


def _deterministic_sql(question: str, item: dict) -> str | None:
    profile = item.get('profile') or {}
    columns = item.get('profile', {}).get('columns_list', [])
    numeric = profile.get('schema', {}).get('numeric_columns', [])
    dates = profile.get('schema', {}).get('date_columns', [])
    dimensions = [column for column in columns if column not in numeric and column not in dates]
    text = question.lower()
    metric = next((column for column in numeric if any(word in column.lower() for word in ('revenue', 'sales', 'amount', 'price', 'cost', 'total', 'profit'))), numeric[0] if numeric else None)
    dimension = next((column for column in dimensions if any(word in column.lower() for word in ('customer', 'product', 'region', 'country', 'category', 'department', 'name'))), dimensions[0] if dimensions else None)
    if any(word in text for word in ('quality', 'missing', 'duplicate', 'clean')):
        return 'SELECT * FROM dataset LIMIT 1'
    if ('trend' in text or 'month' in text or 'time' in text) and dates and metric:
        return f'SELECT strftime(\'%Y-%m\', {_quote(dates[0])}) AS period, SUM({_quote(metric)}) AS value FROM dataset GROUP BY period ORDER BY period'
    if any(word in text for word in ('top', 'most', 'highest', 'best')) and metric and dimension:
        limit = 50 if '50' in text else 20
        return f'SELECT {_quote(dimension)} AS dimension, SUM({_quote(metric)}) AS value FROM dataset GROUP BY {_quote(dimension)} ORDER BY value DESC LIMIT {limit}'
    if metric and any(word in text for word in ('average', 'mean', 'sum', 'total', 'how much', 'revenue', 'sales')):
        aggregate = 'AVG' if any(word in text for word in ('average', 'mean')) else 'SUM'
        return f'SELECT {aggregate}({_quote(metric)}) AS value FROM dataset'
    return None


def _gemini_sql(question: str, item: dict) -> str | None:
    if not settings.gemini_api_key:
        return None
    schema = item.get('profile', {}).get('schema', {})
    columns = item.get('profile', {}).get('columns_list', [])
    prompt = f'''Return only one SQLite SELECT query for the question. The table is dataset. Allowed columns are {columns}. Never use markdown, semicolons, or write operations. Question: {question}'''
    try:
        from google import genai
        text = genai.Client(api_key=settings.gemini_api_key).models.generate_content(model=settings.gemini_model, contents=prompt).text or ''
        return text.replace('```sql', '').replace('```', '').strip()
    except Exception:
        return None


@app.get('/health')
def health():
    return {'status': 'ok', 'service': 'pivot-analytics'}


@app.post('/api/datasets')
async def profile(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(400, 'File name is required.')
    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(415, 'Supported files are CSV, Excel, JSON, and Parquet.')
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, 'Files must be 25MB or smaller.')
    try:
        frame = prepare_frame(_read_bytes(data, suffix))
    except Exception as error:
        raise HTTPException(422, f'Could not read file: {error}') from error
    if frame.empty:
        raise HTTPException(422, 'The uploaded file contains no records.')
    dataset_id = create_dataset(file.filename, suffix, data)
    result = _profile_payload(frame, file.filename, dataset_id)
    context = [f'Dataset: {file.filename}', f'Role: {result["role"]}', f'Rows: {result["rows"]}', f'Columns: {", ".join(frame.columns.astype(str).tolist())}', frame.head(25).to_csv(index=False)]
    add_chunks(dataset_id, file.filename, context + extract(file.filename, data))
    finish_dataset(dataset_id, result)
    return result


@app.post('/api/profile')
async def legacy_profile(file: UploadFile = File(...)):
    return await profile(file)


@app.get('/api/datasets/{dataset_id}')
def dataset(dataset_id: str):
    item = _dataset_or_404(dataset_id)
    item['events'] = events_for(dataset_id)
    item['reports'] = reports_for(dataset_id)
    return item


@app.get('/api/datasets/{dataset_id}/overview')
def overview(dataset_id: str):
    item = _dataset_or_404(dataset_id)
    return _overview(_read_source(item), item['profile'] or {})


@app.get('/api/datasets/{dataset_id}/analyses')
def analyses(dataset_id: str):
    item = _dataset_or_404(dataset_id)
    return {'analyses': _analyses(_read_source(item), item['profile'] or {})}


@app.post('/api/datasets/{dataset_id}/analyses/run')
def run_analysis(dataset_id: str, body: AnalysisRequest):
    item = _dataset_or_404(dataset_id)
    frame = _read_source(item)
    profile = item['profile'] or {}
    if body.kind == 'quality':
        return {'kind': body.kind, 'title': 'Data quality review', 'profile': profile, 'rows': []}
    column = body.column
    if not column or column not in frame.columns:
        raise HTTPException(422, 'This analysis column is not available in the dataset.')
    if body.kind == 'distribution':
        values = _numeric_series(frame, column).dropna()
        if values.empty:
            raise HTTPException(422, 'This field does not contain usable numeric values.')
        histogram = pd.cut(values, bins=min(10, max(2, values.nunique())), duplicates='drop').value_counts().sort_index()
        chart = [{'label': str(label), 'value': int(value)} for label, value in histogram.items()]
        metrics = {'count': int(values.size), 'min': round(float(values.min()), 2), 'max': round(float(values.max()), 2), 'mean': round(float(values.mean()), 2), 'median': round(float(values.median()), 2)}
        return {'kind': body.kind, 'title': f'Distribution of {column}', 'field': column, 'aggregation': 'value frequency', 'metrics': metrics, 'columns': ['range', 'count'], 'chart': chart}
    if body.kind == 'breakdown':
        counts = frame[column].fillna('(blank)').astype(str).value_counts().head(25)
        chart = [{'label': str(label), 'value': int(value)} for label, value in counts.items()]
        return {'kind': body.kind, 'title': f'Breakdown by {column}', 'field': column, 'aggregation': 'row count', 'metrics': {'groups': len(chart), 'rows_in_top_groups': sum(point['value'] for point in chart)}, 'columns': [column, 'count'], 'chart': chart}
    dates = profile.get('schema', {}).get('date_columns', [])
    if not dates:
        raise HTTPException(422, 'A date field is required for a trend analysis.')
    grouped = pd.DataFrame({'period': pd.to_datetime(frame[dates[0]], errors='coerce').dt.to_period('M').astype('string'), 'value': _numeric_series(frame, column)}).dropna().groupby('period', as_index=False)['value'].sum()
    chart = [{'label': str(row['period']), 'value': round(float(row['value']), 2)} for _, row in grouped.iterrows()]
    result = {'kind': body.kind, 'title': f'Trend of {column}', 'field': column, 'aggregation': 'monthly sum', 'columns': ['period', column], 'chart': chart}
    result['metrics'] = _analysis_summary(body.kind, column, {'rows': [{'period': point['label'], 'value': point['value']} for point in chart]}, profile)
    return result


@app.get('/api/datasets/{dataset_id}/events')
async def stream_events(dataset_id: str):
    _dataset_or_404(dataset_id)
    async def feed():
        sent = set()
        for _ in range(15):
            for item in reversed(events_for(dataset_id)):
                key = f"{item['created_at']}-{item['message']}"
                if key not in sent:
                    sent.add(key)
                    yield f"event: analysis\ndata: {json.dumps(item)}\n\n"
            await asyncio.sleep(1)
    return StreamingResponse(feed(), media_type='text/event-stream')


@app.post('/api/datasets/{dataset_id}/transformations')
def plan_transformation(dataset_id: str, body: TransformRequest):
    _dataset_or_404(dataset_id)
    return {'ok': True, 'message': 'Choose Preview to inspect this transformation before approval.'}


@app.post('/api/datasets/{dataset_id}/transformations/{operation}/preview')
def preview_transformation(dataset_id: str, operation: str):
    item = _dataset_or_404(dataset_id)
    if operation not in {'trim_text', 'remove_duplicates', 'normalize_columns', 'parse_dates', 'fill_missing', 'remove_outliers'}:
        raise HTTPException(422, 'Unsupported transformation.')
    source = _read_source(item)
    try:
        clean, metrics = apply(source.copy(), operation)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    metrics = {**metrics, 'rows_before': len(source), 'rows_after': len(clean)}
    transformation_id = create_transformation(dataset_id, operation, str(FILES / f'preview_{dataset_id}_{uuid4().hex}.csv'), metrics)
    transformation = get_transformation(transformation_id)
    preview_path = Path(transformation['preview_path'])
    preview_path.write_text(clean.to_csv(index=False), encoding='utf-8')
    before_preview = json.loads(source.head(8).fillna('').to_json(orient='records'))
    after_preview = json.loads(clean.head(8).fillna('').to_json(orient='records'))
    return {'id': transformation_id, 'operation': operation, 'metrics': metrics, 'rows_before': len(source), 'rows_after': len(clean), 'before': {'rows': len(source), 'columns': [str(column) for column in source.columns], 'preview': before_preview}, 'after': {'rows': len(clean), 'columns': [str(column) for column in clean.columns], 'preview': after_preview}, 'before_preview': before_preview, 'after_preview': after_preview, 'source_unchanged': True}


@app.post('/api/datasets/{dataset_id}/transformations/{transformation_id}/approve')
def approve_transformation(dataset_id: str, transformation_id: str):
    item = _dataset_or_404(dataset_id)
    transformation = get_transformation(transformation_id)
    if not transformation or transformation['dataset_id'] != dataset_id or transformation['status'] != 'pending':
        raise HTTPException(404, 'Pending transformation preview not found.')
    preview = Path(transformation['preview_path'])
    if not preview.exists():
        raise HTTPException(404, 'Transformation preview is unavailable.')
    version_number = len(item['versions'])
    output = FILES / f'{dataset_id}_version_{version_number}.csv'
    output.write_bytes(preview.read_bytes())
    cleaned = pd.read_csv(output)
    cleaned_profile = _profile_payload(cleaned, item['name'], dataset_id)
    detail = {'output': str(output), 'metrics': transformation['metrics'], 'profile': cleaned_profile, 'source_unchanged': True}
    version_id = add_version(dataset_id, f'executed:{transformation["operation"]}', json.dumps(detail))
    activate_dataset_version(dataset_id, str(output), cleaned_profile)
    resolve_transformation(transformation_id, 'approved')
    preview.unlink(missing_ok=True)
    return {'ok': True, 'version': version_number, 'version_id': version_id, 'rows_before': transformation['metrics'].get('rows_before'), 'rows_after': transformation['metrics'].get('rows_after'), 'metrics': transformation['metrics'], 'output': str(output), 'profile': cleaned_profile, 'source_unchanged': True}


@app.post('/api/datasets/{dataset_id}/versions/{number}/activate')
def activate_version(dataset_id: str, number: int):
    item = _dataset_or_404(dataset_id)
    versions = [version for version in item['versions'] if version['number'] == number]
    if not versions:
        raise HTTPException(404, 'Version not found.')
    if number == 0:
        path = _absolute_path(item['source_path'])
        profile = _profile_payload(_read_source({**item, 'active_path': item['source_path']}), item['name'], dataset_id)
    else:
        detail = json.loads(versions[0]['detail'])
        path = _absolute_path(detail['output'])
        profile = detail.get('profile') or _profile_payload(pd.read_csv(path), item['name'], dataset_id)
    if not path.exists() or path.parent.resolve() != FILES.resolve():
        raise HTTPException(404, 'Version output is unavailable.')
    activate_dataset_version(dataset_id, str(path), profile)
    return {'ok': True, 'active_version': number, 'profile': profile}


@app.get('/api/datasets/{dataset_id}/versions/compare')
def compare_versions(dataset_id: str, from_version: int = 0, to_version: int = 0):
    item = _dataset_or_404(dataset_id)
    def path_for(number: int) -> Path:
        if number == 0:
            return _absolute_path(item['source_path'])
        version = next((value for value in item['versions'] if value['number'] == number), None)
        if not version:
            raise HTTPException(404, f'Version {number} not found.')
        return Path(json.loads(version['detail'])['output'])
    before, after = path_for(from_version), path_for(to_version)
    if not before.exists() or not after.exists():
        raise HTTPException(404, 'One of the requested version outputs is unavailable.')
    before_frame, after_frame = pd.read_csv(before), pd.read_csv(after)
    return {'from_version': from_version, 'to_version': to_version, 'rows_before': len(before_frame), 'rows_after': len(after_frame), 'columns_before': before_frame.columns.tolist(), 'columns_after': after_frame.columns.tolist(), 'added_columns': [column for column in after_frame.columns if column not in before_frame.columns], 'removed_columns': [column for column in before_frame.columns if column not in after_frame.columns]}


@app.post('/api/datasets/{dataset_id}/transformations/{transformation_id}/reject')
def reject_transformation(dataset_id: str, transformation_id: str):
    _dataset_or_404(dataset_id)
    transformation = get_transformation(transformation_id)
    if not transformation or transformation['dataset_id'] != dataset_id or transformation['status'] != 'pending':
        raise HTTPException(404, 'Pending transformation preview not found.')
    Path(transformation['preview_path']).unlink(missing_ok=True)
    resolve_transformation(transformation_id, 'rejected')
    return {'ok': True, 'message': 'Transformation rejected; the source remains unchanged.'}


@app.post('/api/datasets/{dataset_id}/transformations/{operation}/execute')
def execute_transformation_compat(dataset_id: str, operation: str):
    preview = preview_transformation(dataset_id, operation)
    return approve_transformation(dataset_id, preview['id'])


@app.post('/api/sql/validate')
def validate_sql(body: SqlRequest):
    _dataset_or_404(body.dataset_id)
    try:
        query = validate_readonly_sql(body.query)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    return {'safe': True, 'query': query, 'explanation': 'Read-only query accepted for the active dataset.'}


@app.post('/api/sql/execute')
def execute_sql(body: SqlRequest):
    item = _dataset_or_404(body.dataset_id)
    try:
        query = validate_readonly_sql(body.query)
        return _execute_frame(_read_source(item), query)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        raise HTTPException(422, f'Could not run this query: {error}') from error


@app.post('/api/sql/generate')
def generate_sql(body: SqlAskRequest):
    item = _dataset_or_404(body.dataset_id)
    query = _deterministic_sql(body.question, item) or _gemini_sql(body.question, item)
    if not query:
        raise HTTPException(422, 'I could not find enough schema evidence to generate a query.')
    try:
        query = validate_readonly_sql(query)
        result = _execute_frame(_read_source(item), query)
    except Exception as error:
        raise HTTPException(422, f'I generated a query that could not be safely executed: {error}') from error
    return result | {'sql': query, 'explanation': 'The query was generated from the detected schema, validated, and executed against the uploaded dataset.'}


@app.get('/api/datasets/{dataset_id}/versions/{number}/download')
def download_version(dataset_id: str, number: int):
    item = _dataset_or_404(dataset_id)
    versions = [version for version in item['versions'] if version['number'] == number]
    if not versions:
        raise HTTPException(404, 'Version not found.')
    if number == 0:
        path = _absolute_path(item['source_path'])
    else:
        detail = json.loads(versions[0]['detail'])
        path = _absolute_path(detail['output'])
    if not path.exists() or path.parent.resolve() != FILES.resolve():
        raise HTTPException(404, 'Generated output is unavailable.')
    media_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' if path.suffix.lower() == '.xlsx' else 'application/octet-stream'
    return FileResponse(path, filename=path.name, media_type=media_type)


@app.post('/api/forecast')
def create_forecast(values: list[float]):
    return forecast(values)


@app.post('/api/scenario')
def run_scenario(body: ScenarioRequest):
    return scenario(body.price_change, body.marketing_change, body.cost_change, body.baseline_revenue)


@app.post('/api/chat')
def chat(body: ChatRequest):
    if not body.dataset_id:
        return {'answer': 'Upload a dataset before asking the analyst to investigate.', 'source': 'guardrail', 'citations': []}
    item = _dataset_or_404(body.dataset_id)
    profile = item.get('profile') or {}
    lower_question = body.question.strip().lower()
    if any(phrase in lower_question for phrase in ('who are you', 'what are you', 'your name', 'what can you do')):
        return {'answer': f"I’m Pivot Analyst, your evidence-backed data analyst. I’m connected to {item['name']} with {profile.get('rows', 0):,} rows and {profile.get('columns', 0)} detected fields. I can investigate trends, highest values, quality issues, and group comparisons by running read-only evidence queries.", 'source': 'pivot-analyst', 'sql': None, 'query_result': None, 'citations': [{'source': item['name'], 'score': 1.0}]}
    if body.question.strip().lower() in {'hi', 'hello', 'hey', 'hiya', 'good morning', 'good afternoon', 'good evening'}:
        return {'answer': f"Hi — I’m connected to {item['name']}. I found {profile.get('rows', 0)} rows and {profile.get('columns', 0)} detected fields. Ask me about trends, quality, categories, or values and I’ll investigate the source.", 'source': 'dataset-aware', 'sql': None, 'citations': [{'source': item['name'], 'score': 1.0}]}
    retrieved = retrieve(body.question, chunks_for(body.dataset_id))
    query = _deterministic_sql(body.question, item) or _gemini_sql(body.question, item)
    evidence: dict[str, Any] = {'profile': {'rows': profile.get('rows'), 'columns': profile.get('columns_list'), 'quality_score': profile.get('quality_score'), 'issues': profile.get('issues'), 'metrics': profile.get('metrics')}, 'retrieved_context': retrieved}
    if query:
        try:
            query = validate_readonly_sql(query)
            evidence['query'] = query
            evidence['query_result'] = _execute_frame(_read_source(item), query)
        except Exception:
            query = None
    sources = [{'source': item['name'], 'score': 1.0}]
    sources.extend({'source': value['source'], 'score': value['score']} for value in retrieved)
    context = json.dumps(evidence, default=str)[:16000]
    if query and evidence.get('query_result'):
        query_result = evidence['query_result']
        rows = query_result.get('rows') or []
        if any(word in lower_question for word in ('highest', 'top', 'most', 'best')) and rows and 'dimension' in rows[0]:
            first = rows[0]
            answer = f"The highest grouped value is {first.get('dimension')} at {float(first.get('value', 0)):,.2f} for the selected metric. I grouped by the detected field and ordered the evidence descending."
        elif ('trend' in lower_question or 'month' in lower_question or 'time' in lower_question) and rows and 'value' in rows[0]:
            values = [float(row.get('value', 0) or 0) for row in rows]
            peak = max(rows, key=lambda row: float(row.get('value', 0) or 0))
            answer = f"The {len(rows)}-period trend totals {sum(values):,.2f}, averaging {sum(values) / len(values):,.2f} per period. The highest period is {peak.get('period') or peak.get('label')} at {max(values):,.2f}."
        elif rows and 'value' in rows[0] and len(rows[0]) == 1:
            answer = f"The evidence result is {float(rows[0]['value']):,.2f}. This was calculated directly from the detected numeric field using a read-only query."
        else:
            answer = f"I found {query_result.get('count', len(rows)):,} evidence rows with fields {', '.join(query_result.get('columns') or rows[0].keys())}. The exact returned records are shown below."
        return {'answer': answer, 'source': 'evidence-query', 'sql': query, 'query_result': query_result, 'citations': sources}
    if settings.gemini_api_key:
        try:
            from google import genai
            prompt = f'''You are Pivot, a senior data analyst. Answer the question only from the evidence below. Do not invent facts, business labels, trends, or recommendations. If the evidence is insufficient, say exactly that. Include the relevant numbers and explain the query evidence in plain language. Never claim a transformation occurred unless the evidence says so.\n\nEvidence:\n{context}\n\nQuestion: {body.question}'''
            response = genai.Client(api_key=settings.gemini_api_key).models.generate_content(model=settings.gemini_model, contents=prompt)
            return {'answer': response.text or 'I could not produce an evidence-backed answer.', 'source': 'gemini-analyst', 'sql': query, 'query_result': evidence.get('query_result'), 'citations': sources}
        except Exception:
            pass
    query_result = evidence.get('query_result') or {}
    if query_result.get('count', 0) or retrieved or profile.get('issues'):
        rows = query_result.get('rows') or []
        sample = '; '.join(', '.join(f'{key}={value}' for key, value in row.items()) for row in rows[:3])
        detail = f" The first evidence rows are: {sample}." if sample else ''
        return {'answer': f"I found evidence in {item['name']} and returned {query_result.get('count', 0)} matching rows.{detail}", 'source': 'deterministic-evidence', 'sql': query, 'query_result': query_result, 'citations': sources}
    return {'answer': f"Hi — I’m connected to {item['name']}. I found {profile.get('rows', 0)} rows and {profile.get('columns', 0)} detected fields. Ask me about trends, quality, categories, or values and I’ll investigate the source.", 'source': 'dataset-aware', 'sql': query, 'citations': sources}


@app.post('/api/datasets/{dataset_id}/reports')
def create_report(dataset_id: str, body: ReportRequest):
    item = _dataset_or_404(dataset_id)
    profile = item.get('profile') or {}
    overview_data = _overview(_read_source(item), profile)
    safe_title = re.sub(r'[^a-zA-Z0-9_-]+', '-', body.title or 'pivot-report').strip('-').lower() or 'pivot-report'
    format_name = body.format.lower()
    if format_name not in {'md', 'csv', 'pdf'}:
        raise HTTPException(422, 'Reports currently support Markdown, CSV, and PDF.')
    payload = {'dataset': item['name'], 'generated_at': pd.Timestamp.utcnow().isoformat(), 'profile': profile, 'overview': overview_data, 'versions': item['versions']}
    if format_name == 'json':
        content, media_type, suffix = json.dumps(payload, indent=2, default=str), 'application/json', 'json'
    else:
        markdown = f"# {body.title or 'Pivot report'}\n\nDataset: **{item['name']}**\n\n## Profile\n\n- Rows: {profile.get('rows', 0)}\n- Columns: {profile.get('columns', 0)}\n- Quality score: {profile.get('quality_score', 0)}/100\n\n## Detected issues\n\n" + '\n'.join(f"- {issue['type']}: {issue['count']} affected rows — {issue['impact']}" for issue in profile.get('issues', []))
        if format_name == 'csv':
            rows = [{'field': 'dataset', 'value': item['name']}, {'field': 'rows', 'value': profile.get('rows', 0)}, {'field': 'columns', 'value': profile.get('columns', 0)}, {'field': 'quality_score', 'value': profile.get('quality_score', 0)}]
            content, media_type, suffix = pd.DataFrame(rows).to_csv(index=False), 'text/csv', 'csv'
        elif format_name == 'pdf':
            lines = markdown.replace('**', '').splitlines()
            escape = lambda value: str(value).encode('latin-1', 'replace').decode('latin-1').replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
            nl = chr(10)
            stream = 'BT /F1 11 Tf 48 760 Td ' + ' '.join(f'({escape(line[:115])}) Tj 0 -16 Td' for line in lines[:42]) + ' ET'
            objects = ['<< /Type /Catalog /Pages 2 0 R >>', '<< /Type /Pages /Kids [3 0 R] /Count 1 >>', '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>', '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>', f'<< /Length {len(stream.encode("latin-1", "replace"))} >>{nl}stream{nl}{stream}{nl}endstream']
            pdf = '%PDF-1.4' + nl; offsets = [0]
            for index, obj in enumerate(objects, 1): offsets.append(len(pdf.encode('latin-1'))); pdf += f'{index} 0 obj{nl}{obj}{nl}endobj{nl}'
            xref = len(pdf.encode('latin-1')); pdf += f'xref{nl}0 {len(objects)+1}{nl}0000000000 65535 f {nl}' + ''.join(f'{offset:010d} 00000 n {nl}' for offset in offsets[1:]) + f'trailer << /Size {len(objects)+1} /Root 1 0 R >>{nl}startxref{nl}{xref}{nl}%%EOF'
            content, media_type, suffix = pdf, 'application/pdf', 'pdf'
        elif format_name == 'html':
            content, media_type, suffix = f'<html><body><pre>{markdown}</pre></body></html>', 'text/html', 'html'
        else:
            content, media_type, suffix = markdown, 'text/markdown', 'md'
    path = FILES / f'{dataset_id}_{safe_title}.{suffix}'
    if suffix == 'pdf':
        path.write_bytes(content.encode('latin-1'))
    else:
        path.write_text(content, encoding='utf-8')
    report_id = add_report(dataset_id, body.title or 'Pivot report', format_name, str(path))
    return {'id': report_id, 'title': body.title or 'Pivot report', 'format': format_name, 'download_url': f'/api/datasets/{dataset_id}/reports/{report_id}/download'}


@app.get('/api/datasets/{dataset_id}/reports/{report_id}/download')
def download_report(dataset_id: str, report_id: str):
    item = _dataset_or_404(dataset_id)
    report = next((report for report in reports_for(dataset_id) if report['id'] == report_id), None)
    if not report:
        raise HTTPException(404, 'Report not found.')
    path = Path(report['path'])
    if not path.exists() or path.parent.resolve() != FILES.resolve():
        raise HTTPException(404, 'Report file is unavailable.')
    return FileResponse(path, filename=path.name)


@app.get('/api/datasets/{dataset_id}/search')
def search_dataset(dataset_id: str, q: str = ''):
    item = _dataset_or_404(dataset_id)
    term = q.strip().lower()
    if not term:
        return {'results': []}
    profile = item.get('profile') or {}
    results = [{'type': 'dataset', 'label': item['name'], 'detail': f"{profile.get('rows', 0)} rows"}] if term in item['name'].lower() else []
    for column in profile.get('columns_list', []):
        if term in column.lower():
            results.append({'type': 'column', 'label': column, 'detail': profile.get('role', 'detected field')})
    for issue in profile.get('issues', []):
        if term in issue['type'].lower() or term in issue['impact'].lower():
            results.append({'type': 'quality', 'label': issue['type'], 'detail': issue['impact']})
    for version in item.get('versions', []):
        if term in version['operation'].lower() or term in version['detail'].lower():
            results.append({'type': 'version', 'label': f"Version {version['number']}", 'detail': version['operation']})
    return {'results': results[:30]}


public = Path('public')
if public.exists():
    app.mount('/', StaticFiles(directory=public, html=True), name='web')
