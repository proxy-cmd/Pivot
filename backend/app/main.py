from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager, contextmanager
from uuid import uuid4
from pathlib import Path
from tempfile import mkstemp
from typing import Any

import pandas as pd
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .assistant import answer_question
from .analytics import _numeric_series, forecast, prepare_frame, profile_frame, scenario
from .autopilot import briefing_markdown, build_report, clean_frame, explore, plan_prompt
from .config import get_settings
from .database import get_engine
from .auth import authenticate_request, current_user_id
from .auth_routes import router as auth_router
from .models import AnalysisRequest, ChatRequest, ReportRequest, ScenarioRequest, SqlAskRequest, SqlRequest, TransformRequest
from .pipeline import apply
from .rag import extract, retrieve
from .security import validate_readonly_sql
from .storage import get_storage
from .store import (
    add_chunks, add_report, add_version, chunks_for, create_dataset, create_transformation,
    event as record_event, events_for, finish_dataset, get_dataset, get_transformation, reports_for, resolve_transformation, activate_dataset_version,
)

settings = get_settings()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings.validate_production()
    get_storage()
    logger.info('Pivot started in %s mode', settings.app_env)
    yield
    get_engine().dispose()


app = FastAPI(title='Pivot Analytics API', version='1.2.0', lifespan=lifespan)
cors_origins = sorted({origin.strip() for origin in settings.cors_origins.split(',') if origin.strip()})
app.add_middleware(SessionMiddleware, secret_key=settings.jwt_secret or 'development-only-oauth-state-secret', https_only=settings.cookie_secure, same_site='lax')
app.add_middleware(CORSMiddleware, allow_origins=cors_origins, allow_credentials=True, allow_methods=['GET', 'POST', 'OPTIONS'], allow_headers=['Content-Type', 'Authorization'])
app.include_router(auth_router)

_requests: dict[str, deque[float]] = defaultdict(deque)


def _is_rate_limited(request: Request) -> bool:
    limits = {
        '/api/auth/google/login': (10, 60),
        '/api/auth/refresh': (30, 60),
        '/api/chat': (40, 60),
        '/api/datasets': (12, 300),
    }
    rule = limits.get(request.url.path)
    if not rule:
        return False
    limit, window = rule
    client = request.client.host if request.client else 'unknown'
    key = f'{request.url.path}:{client}'
    now = time.monotonic()
    entries = _requests[key]
    while entries and entries[0] <= now - window:
        entries.popleft()
    if len(entries) >= limit:
        return True
    entries.append(now)
    return False


def _trusted_origin(request: Request) -> bool:
    origin = request.headers.get('origin')
    if not origin:
        return True
    allowed = {value.strip().rstrip('/') for value in cors_origins}
    return origin.rstrip('/') in allowed


@app.middleware('http')
async def authentication_middleware(request: Request, call_next):
    path = request.url.path
    if _is_rate_limited(request):
        return JSONResponse({'detail': 'Too many requests. Please try again shortly.'}, status_code=429, headers={'Retry-After': '60'})
    if request.method == 'OPTIONS' or path in {'/health', '/docs', '/openapi.json', '/redoc'} or path.startswith('/api/auth/'):
        return await call_next(request)
    if not path.startswith('/api/'):
        return await call_next(request)
    if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'} and request.cookies.get('pivot_access') and not _trusted_origin(request):
        return JSONResponse({'detail': 'Request origin is not allowed.'}, status_code=403)
    try:
        user = authenticate_request(request)
    except HTTPException as error:
        return JSONResponse({'detail': error.detail}, status_code=error.status_code, headers=error.headers)
    request.state.user = user
    token = current_user_id.set(user['id'])
    try:
        return await call_next(request)
    finally:
        current_user_id.reset(token)


@app.middleware('http')
async def security_headers(request: Request, call_next):
    request_id = uuid4().hex
    try:
        response = await call_next(request)
    except Exception:
        logger.exception('Unhandled request error id=%s path=%s', request_id, request.url.path)
        return JSONResponse({'detail': 'An unexpected error occurred.', 'request_id': request_id}, status_code=500)
    response.headers['X-Request-ID'] = request_id
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    response.headers['Content-Security-Policy'] = "default-src 'self'; connect-src 'self'; img-src 'self' data: https:; style-src 'self' 'unsafe-inline'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
    if settings.cookie_secure:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
MAX_CONTEXT_BYTES = 5 * 1024 * 1024
ALLOWED_SUFFIXES = {'.csv', '.xlsx', '.xls', '.json', '.parquet'}
CONTEXT_SUFFIXES = {'.pdf', '.txt', '.md', '.json'}
ALLOWED_UPLOAD_TYPES = {
    'application/octet-stream', 'text/csv', 'application/csv', 'application/json',
    'application/vnd.ms-excel', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/vnd.apache.parquet', 'application/x-parquet',
}
ALLOWED_CONTEXT_TYPES = {'application/octet-stream', 'application/pdf', 'text/plain', 'text/markdown', 'application/json'}
MAX_UPLOAD_BYTES = settings.upload_max_bytes
MAX_UPLOAD_ROWS = settings.upload_max_rows


def _dataset_or_404(dataset_id: str) -> dict:
    item = get_dataset(dataset_id)
    if not item:
        raise HTTPException(404, 'Dataset session not found.')
    return item


def _validate_upload_name(filename: str) -> None:
    if len(filename) > 255 or Path(filename).name != filename or any(ord(char) < 32 for char in filename):
        raise HTTPException(400, 'Invalid file name.')


def _read_file(source: Path, suffix: str) -> pd.DataFrame:
    if suffix in ('.xlsx', '.xls'):
        return pd.read_excel(source)
    if suffix == '.json':
        return pd.read_json(source)
    if suffix == '.parquet':
        return pd.read_parquet(source)
    return pd.read_csv(source)


@contextmanager
def _temporary_path(suffix: str):
    descriptor, name = mkstemp(suffix=suffix)
    os.close(descriptor)
    path = Path(name)
    try:
        yield path
    finally:
        path.unlink(missing_ok=True)


def _read_source(item: dict) -> pd.DataFrame:
    try:
        with get_storage().local_file(item.get('active_path') or item['source_path']) as path:
            if not path.exists():
                raise FileNotFoundError(path)
            frame = _read_file(path, path.suffix.lower())
    except Exception as error:
        raise HTTPException(422, f'Could not read the preserved source: {error}') from error
    frame = prepare_frame(frame)
    profile = item.get('profile') or {}
    for column in profile.get('schema', {}).get('numeric_columns', []):
        if column in frame.columns:
            frame[column] = _numeric_series(frame, column)
    return frame


def _save_frame(item: dict, frame: pd.DataFrame, name: str) -> str:
    key = get_storage().key(item['owner_user_id'], item['id'], name, '.csv')
    with _temporary_path('.csv') as path:
        frame.to_csv(path, index=False)
        get_storage().upload_file(path, key)
    return key


def _save_text(item: dict, text: str, name: str, suffix: str) -> str:
    key = get_storage().key(item['owner_user_id'], item['id'], name, suffix)
    with _temporary_path(suffix) as path:
        path.write_text(text, encoding='utf-8')
        get_storage().upload_file(path, key)
    return key


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
        'negative_values': ('remove_outliers', 'Review negative and extreme numeric values'),
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
    try:
        with get_engine().connect() as connection:
            connection.exec_driver_sql('SELECT 1')
    except Exception as error:
        logger.warning('Readiness check failed: %s', type(error).__name__)
        raise HTTPException(503, 'Database is unavailable.') from error
    return {'status': 'ok', 'service': 'pivot-analytics'}


@app.post('/api/datasets')
async def profile(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(400, 'File name is required.')
    _validate_upload_name(file.filename)
    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(415, 'Supported files are CSV, Excel, JSON, and Parquet.')
    if file.content_type not in ALLOWED_UPLOAD_TYPES:
        raise HTTPException(415, 'The uploaded content type is not supported.')
    dataset_id = uuid4().hex
    with _temporary_path(suffix) as path:
        size = 0
        with path.open('wb') as handle:
            while chunk := await file.read(64 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, f'Files must be {MAX_UPLOAD_BYTES // 1024 // 1024}MB or smaller.')
                handle.write(chunk)
        try:
            frame = prepare_frame(_read_file(path, suffix))
        except Exception as error:
            raise HTTPException(422, f'Could not read file: {error}') from error
        if frame.empty:
            raise HTTPException(422, 'The uploaded file contains no records.')
        if len(frame) > MAX_UPLOAD_ROWS:
            raise HTTPException(413, f'Datasets must contain {MAX_UPLOAD_ROWS:,} rows or fewer.')
        user_id = current_user_id.get()
        key = get_storage().key(user_id, dataset_id, 'source', suffix)
        get_storage().upload_file(path, key)
    create_dataset(file.filename, key, dataset_id)
    result = _profile_payload(frame, file.filename, dataset_id)
    context = [f'Dataset: {file.filename}', f'Role: {result["role"]}', f'Rows: {result["rows"]}', f'Columns: {", ".join(frame.columns.astype(str).tolist())}', frame.head(25).to_csv(index=False)]
    add_chunks(dataset_id, file.filename, context)
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


@app.post('/api/datasets/{dataset_id}/context')
async def add_dataset_context(dataset_id: str, file: UploadFile = File(...)):
    """Attach a business glossary or data dictionary to a dataset's RAG context."""
    _dataset_or_404(dataset_id)
    if not file.filename:
        raise HTTPException(400, 'A context file name is required.')
    _validate_upload_name(file.filename)
    suffix = Path(file.filename).suffix.lower()
    if suffix not in CONTEXT_SUFFIXES:
        raise HTTPException(415, 'Context files must be PDF, TXT, Markdown, or JSON.')
    if file.content_type not in ALLOWED_CONTEXT_TYPES:
        raise HTTPException(415, 'The context content type is not supported.')
    raw = await file.read(MAX_CONTEXT_BYTES + 1)
    if len(raw) > MAX_CONTEXT_BYTES:
        raise HTTPException(413, 'Context files must be 5MB or smaller.')
    try:
        parts = extract(file.filename, raw)
    except Exception as error:
        raise HTTPException(422, f'Could not read context file: {error}') from error
    if not parts:
        raise HTTPException(422, 'The context file contains no readable text.')
    add_chunks(dataset_id, file.filename, parts)
    record_event(dataset_id, 'context', f'Business context attached: {file.filename} ({len(parts)} chunks).')
    return {'source': file.filename, 'chunks': len(parts)}


@app.post('/api/datasets/{dataset_id}/autopilot')
def run_autopilot(dataset_id: str):
    """Run the safe, local-first one-click analysis workflow."""
    item = _dataset_or_404(dataset_id)
    source = _read_source(item)
    cleaned, steps = clean_frame(source)
    cleaned_profile = _profile_payload(cleaned, item['name'], dataset_id)
    facts = explore(cleaned, cleaned_profile)
    plan = None
    if settings.gemini_api_key:
        plan = extract_json(call_gemini(plan_prompt(cleaned_profile, facts)) or '')
    report = build_report(cleaned, cleaned_profile, steps, plan, facts)

    version_number = len(item['versions'])
    output = _save_frame(item, cleaned, f'version-{version_number}-autopilot')
    detail = {
        'output': output,
        'source_unchanged': True,
        'metrics': {'rows_before': len(source), 'rows_after': len(cleaned), 'steps': steps},
        'profile': cleaned_profile,
        'autopilot': report,
    }
    version_id = add_version(dataset_id, 'auto_pilot', json.dumps(detail))
    activate_dataset_version(dataset_id, output, cleaned_profile)

    briefing = briefing_markdown(item['name'], report, cleaned_profile)
    briefing_path = _save_text(item, briefing, 'auto-pilot-briefing', '.md')
    report_id = add_report(dataset_id, 'Auto Pilot briefing', 'md', briefing_path)

    return {
        **report,
        'profile': cleaned_profile,
        'version': version_number,
        'version_id': version_id,
        'download_url': f'/api/datasets/{dataset_id}/versions/{version_number}/download',
        'briefing_url': f'/api/datasets/{dataset_id}/reports/{report_id}/download',
        'source_unchanged': True,
    }


@app.get('/api/datasets/{dataset_id}/autopilot')
def latest_autopilot(dataset_id: str):
    item = _dataset_or_404(dataset_id)
    for version in reversed(item['versions']):
        if version['operation'] != 'auto_pilot':
            continue
        detail = json.loads(version['detail'])
        report = detail.get('autopilot')
        if report:
            briefing = next((entry for entry in reports_for(dataset_id) if entry['title'] == 'Auto Pilot briefing'), None)
            return {
                **report,
                'profile': detail.get('profile', item.get('profile')),
                'version': version['number'],
                'version_id': version['id'],
                'download_url': f"/api/datasets/{dataset_id}/versions/{version['number']}/download",
                'briefing_url': f"/api/datasets/{dataset_id}/reports/{briefing['id']}/download" if briefing else None,
                'source_unchanged': True,
            }
    return {'report': None}


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
    if operation not in {'trim_text', 'remove_duplicates', 'normalize_columns', 'parse_dates', 'fill_missing', 'remove_outliers', 'standardize_format'}:
        raise HTTPException(422, 'Unsupported transformation.')
    source = _read_source(item)
    try:
        clean, metrics = apply(source.copy(), operation)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    metrics = {**metrics, 'rows_before': len(source), 'rows_after': len(clean)}
    preview_key = _save_frame(item, clean, f'preview-{uuid4().hex}')
    transformation_id = create_transformation(dataset_id, operation, preview_key, metrics)
    before_preview = json.loads(
    source.head(8)
    .astype(object)
    .where(source.head(8).notna(), None)
    .to_json(orient="records")
)

    after_preview = json.loads(
    clean.head(8)
    .astype(object)
    .where(clean.head(8).notna(), None)
    .to_json(orient="records")
)
    return {'id': transformation_id, 'operation': operation, 'metrics': metrics, 'rows_before': len(source), 'rows_after': len(clean), 'before': {'rows': len(source), 'columns': [str(column) for column in source.columns], 'preview': before_preview}, 'after': {'rows': len(clean), 'columns': [str(column) for column in clean.columns], 'preview': after_preview}, 'before_preview': before_preview, 'after_preview': after_preview, 'source_unchanged': True}


@app.post('/api/datasets/{dataset_id}/transformations/{transformation_id}/approve')
def approve_transformation(dataset_id: str, transformation_id: str):
    item = _dataset_or_404(dataset_id)
    transformation = get_transformation(transformation_id)
    if not transformation or transformation['dataset_id'] != dataset_id or transformation['status'] != 'pending':
        raise HTTPException(404, 'Pending transformation preview not found.')
    version_number = len(item['versions'])
    try:
        with get_storage().local_file(transformation['preview_path']) as preview:
            cleaned = pd.read_csv(preview)
    except Exception as error:
        raise HTTPException(404, 'Transformation preview is unavailable.') from error
    output = _save_frame(item, cleaned, f'version-{version_number}')
    cleaned_profile = _profile_payload(cleaned, item['name'], dataset_id)
    detail = {'output': output, 'metrics': transformation['metrics'], 'profile': cleaned_profile, 'source_unchanged': True}
    version_id = add_version(dataset_id, f'executed:{transformation["operation"]}', json.dumps(detail))
    activate_dataset_version(dataset_id, output, cleaned_profile)
    resolve_transformation(transformation_id, 'approved')
    get_storage().delete(transformation['preview_path'])
    return {'ok': True, 'version': version_number, 'version_id': version_id, 'rows_before': transformation['metrics'].get('rows_before'), 'rows_after': transformation['metrics'].get('rows_after'), 'metrics': transformation['metrics'], 'output': str(output), 'profile': cleaned_profile, 'source_unchanged': True}


@app.post('/api/datasets/{dataset_id}/versions/{number}/activate')
def activate_version(dataset_id: str, number: int):
    item = _dataset_or_404(dataset_id)
    versions = [version for version in item['versions'] if version['number'] == number]
    if not versions:
        raise HTTPException(404, 'Version not found.')
    if number == 0:
        path = item['source_path']
        profile = _profile_payload(_read_source({**item, 'active_path': item['source_path']}), item['name'], dataset_id)
    else:
        detail = json.loads(versions[0]['detail'])
        path = detail['output']
        profile = detail.get('profile') or _profile_payload(_read_source({**item, 'active_path': path}), item['name'], dataset_id)
    activate_dataset_version(dataset_id, path, profile)
    return {'ok': True, 'active_version': number, 'profile': profile}


@app.get('/api/datasets/{dataset_id}/versions/compare')
def compare_versions(dataset_id: str, from_version: int = 0, to_version: int = 0):
    item = _dataset_or_404(dataset_id)
    def path_for(number: int) -> str:
        if number == 0:
            return item['source_path']
        version = next((value for value in item['versions'] if value['number'] == number), None)
        if not version:
            raise HTTPException(404, f'Version {number} not found.')
        return json.loads(version['detail'])['output']
    before, after = path_for(from_version), path_for(to_version)
    try:
        before_frame = _read_source({**item, 'active_path': before})
        after_frame = _read_source({**item, 'active_path': after})
    except HTTPException:
        raise HTTPException(404, 'One of the requested version outputs is unavailable.')
    return {'from_version': from_version, 'to_version': to_version, 'rows_before': len(before_frame), 'rows_after': len(after_frame), 'columns_before': before_frame.columns.tolist(), 'columns_after': after_frame.columns.tolist(), 'added_columns': [column for column in after_frame.columns if column not in before_frame.columns], 'removed_columns': [column for column in before_frame.columns if column not in after_frame.columns]}


@app.post('/api/datasets/{dataset_id}/transformations/{transformation_id}/reject')
def reject_transformation(dataset_id: str, transformation_id: str):
    _dataset_or_404(dataset_id)
    transformation = get_transformation(transformation_id)
    if not transformation or transformation['dataset_id'] != dataset_id or transformation['status'] != 'pending':
        raise HTTPException(404, 'Pending transformation preview not found.')
    get_storage().delete(transformation['preview_path'])
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
        path = item['source_path']
    else:
        detail = json.loads(versions[0]['detail'])
        path = detail['output']
    filename = Path(path).name
    return StreamingResponse(get_storage().stream(path), media_type='application/octet-stream', headers={'Content-Disposition': f'attachment; filename="{filename}"'})


@app.post('/api/forecast')
def create_forecast(values: list[float]):
    return forecast(values)


@app.post('/api/scenario')
def run_scenario(body: ScenarioRequest):
    return scenario(body.price_change, body.marketing_change, body.cost_change, body.baseline_revenue)


def _requested_transformation(question: str) -> str | None:
    """Map an explicit cleaning request to one safe, versioned operation."""
    text = question.lower()
    tokens = set(re.findall(r'[a-z]+', text))
    action_words = ('fix', 'clean', 'standardize', 'normalize', 'format', 'remove', 'fill', 'correct', 'update')
    if not any(word in tokens for word in action_words):
        return None
    if any(word in tokens for word in ('outlier', 'outliers', 'anomal')) or 'extreme value' in text:
        return 'remove_outliers'
    if any(word in tokens for word in ('duplicate', 'duplicates')) or 'repeated row' in text:
        return 'remove_duplicates'
    if any(word in tokens for word in ('missing', 'null', 'blank')):
        return 'fill_missing'
    if any(word in tokens for word in ('date', 'dates', 'timestamp')) or 'time format' in text:
        return 'parse_dates'
    if any(phrase in text for phrase in ('column name', 'field name', 'headers')):
        return 'normalize_columns'
    if any(word in tokens for word in ('whitespace', 'spaces', 'trim')):
        return 'trim_text'
    if any(word in tokens for word in ('format', 'formats', 'messy', 'standard', 'standardize')) or 'clean data' in text:
        return 'standardize_format'
    return None


@app.post('/api/chat-legacy')
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


def call_gemini(prompt: str) -> str | None:
    settings = get_settings()
    if not settings.gemini_api_key:
        return None
    try:
        from google import genai
        client = genai.Client(api_key=settings.gemini_api_key)
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt
        )
        return response.text
    except Exception:
        logger.warning('Gemini call failed.')
        return None


def extract_json(text: str) -> dict | None:
    if not text:
        return None
    try:
        # Find json block ```json ... ```
        match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
        if match:
            return json.loads(match.group(1).strip())
        
        # Try raw json parsing
        cleaned = text.strip()
        if cleaned.startswith('{') and cleaned.endswith('}'):
            return json.loads(cleaned)
            
        # Try finding first { and last }
        start = cleaned.find('{')
        end = cleaned.rfind('}')
        if start != -1 and end != -1:
            return json.loads(cleaned[start:end+1])
    except Exception:
        pass
    return None


@app.post('/api/chat')
def chat_v2(body: ChatRequest):
    """Answer in analyst format: prose, insights, chart data and evidence rows."""
    if not body.dataset_id:
        return {'answer': 'Upload a dataset before asking the analyst to investigate.', 'source': 'guardrail', 'citations': []}
    
    item = _dataset_or_404(body.dataset_id)
    profile = item.get('profile') or {}
    question = body.question.strip()
    history = (body.context.get('history') or []) if isinstance(body.context, dict) else []
    retrieved = retrieve(question, chunks_for(body.dataset_id))
    citations = [{'source': item['name'], 'score': 1.0}]
    citations.extend({'source': value['source'], 'score': value['score']} for value in retrieved)

    # --- Step 1: AI Routing ---
    intent = "general_chat"
    sql_query = None
    cleaning_op = None
    reasoning = ""
    conversation_answer = None
    
    if settings.gemini_api_key:
        columns_list = profile.get('columns_list', [])
        schema_info = profile.get('schema', {})
        issues = profile.get('issues', [])
        
        metadata = {
            'dataset_name': item['name'],
            'rows': profile.get('rows', 0),
            'columns': columns_list,
            'numeric_columns': schema_info.get('numeric_columns', []),
            'date_columns': schema_info.get('date_columns', []),
            'issues': [{'type': iss['type'], 'count': iss['count']} for iss in issues]
        }
        
        history_formatted = []
        for entry in history[-6:]:
            role = entry.get('role', '')
            text_content = entry.get('text', '')
            if text_content:
                history_formatted.append(f"{'User' if role == 'user' else 'Analyst'}: {text_content}")
                
        router_prompt = f"""You are the routing and analysis agent for Pivot, an intelligent data analyst platform.
Your task is to analyze the user's question and determine the appropriate action.

Identity policy:
- You are always "Pivot Analyst" inside the Pivot product.
- Do not claim to be Google, Gemini, or any other provider; do not mention underlying model providers.
- Do not imply affiliation, endorsement, or ownership by any third party.
- If asked who made you or what you are, describe yourself only as Pivot's evidence-first data analyst.

Dataset Profile:
{json.dumps(metadata, indent=2)}

Conversation History:
{chr(10).join(history_formatted)}

User Question: "{question}"

You must choose one of the following intents:
1. "query": The user is asking to calculate, search, aggregate, filter, group, or inspect numerical/categorical data. Write a single, valid SQLite SELECT query to run against the 'dataset' table to get the supporting evidence.
   - Do NOT write delete, insert, update or alter queries.
   - Ensure the query uses exact column names from the Profile.
   - For yearly/monthly trend grouping, use `strftime('%Y-%m', date_column)` or `strftime('%Y', date_column)`.
2. "cleaning": The user wants to clean, format, normalize column names, parse dates, trim whitespace, fill missing nulls, remove duplicates, or handle outliers.
   - Set 'cleaning_operation' to one of: 'trim_text', 'remove_duplicates', 'normalize_columns', 'parse_dates', 'fill_missing', 'remove_outliers', 'standardize_format'.
3. "general_chat": The user is having a general conversation or asking about Pivot rather than requesting a dataset operation. Write a direct, helpful response without inventing dataset facts.

Respond ONLY with a JSON block in this exact format (no markdown except the json container):
```json
{{
  "intent": "query" | "cleaning" | "general_chat",
  "sql": "SELECT ...", // required only if intent is 'query'
  "cleaning_operation": "operation_name", // required only if intent is 'cleaning'
  "answer": "A concise response", // required only if intent is 'general_chat'
  "reasoning": "Brief explanation of your decision"
}}
```"""
        
        router_response = call_gemini(router_prompt)
        router_json = extract_json(router_response)
        
        if router_json:
            intent = router_json.get('intent', 'general_chat')
            sql_query = router_json.get('sql')
            cleaning_op = router_json.get('cleaning_operation')
            conversation_answer = router_json.get('answer')
            reasoning = router_json.get('reasoning', '')

    if intent == 'general_chat' and isinstance(conversation_answer, str) and conversation_answer.strip():
        return {'answer': conversation_answer.strip(), 'source': 'pivot-analyst', 'intent': 'conversation', 'sql': None, 'query_result': None, 'rows': [], 'insights': [], 'driver_rows': [], 'visualization': None, 'action': None, 'download_url': None, 'citations': citations}

    # --- Step 2: Intent Execution ---
    
    # 2.1 Cleaning/Formatting request
    if intent == 'cleaning' and cleaning_op:
        try:
            preview = preview_transformation(body.dataset_id, cleaning_op)
            preview_rows = preview.get('after_preview') or []
            preview_columns = list(preview_rows[0].keys()) if preview_rows else []
            action = {'type': 'transformation', 'operation': cleaning_op, 'metrics': preview.get('metrics', {}), 'preview_id': preview.get('id')}
            
            if cleaning_op != 'remove_outliers':
                approved = approve_transformation(body.dataset_id, preview['id'])
                version = approved['version']
                action.update({'status': 'approved', 'version': version})
                
                explanation = f"Done. I analyzed your dataset and dynamically executed the cleanup operation: **{cleaning_op.replace('_', ' ')}**. Standardized values are versioned and ready as version {version}."
                if settings.gemini_api_key:
                    try:
                        explain_prompt = f"Explain to the user in a friendly senior data analyst tone that you've just executed the dataset cleaning operation '{cleaning_op}' successfully, resulting in version {version}. Summarize the impact: rows changed from {preview.get('rows_before')} to {preview.get('rows_after')}."
                        res = call_gemini(explain_prompt)
                        if res:
                            explanation = res.strip()
                    except Exception:
                        pass
                
                return {
                    'answer': explanation,
                    'source': 'pivot-analyst', 'intent': 'transformation', 'sql': None,
                    'query_result': {'columns': preview_columns, 'rows': preview_rows[:10], 'count': len(preview_rows)},
                    'rows': preview_rows[:10], 'insights': [f"Rows: {approved.get('rows_before', 0):,} → {approved.get('rows_after', 0):,}.", 'The updated version is saved in your versions timeline.'],
                    'driver_rows': [], 'visualization': None, 'evidence': {'operation': cleaning_op, 'version': version},
                    'action': action, 'download_url': f"/api/datasets/{body.dataset_id}/versions/{version}/download", 'citations': citations,
                }
            else:
                return {
                    'answer': "I prepared a preview for outlier removal. Outliers can represent legitimate spikes, so review the proposed changes in Cleaning.",
                    'source': 'pivot-analyst', 'intent': 'transformation-preview', 'sql': None,
                    'query_result': {'columns': preview_columns, 'rows': preview_rows[:10], 'count': len(preview_rows)},
                    'rows': preview_rows[:10], 'insights': [f"Proposed: {preview.get('rows_before', 0):,} → {preview.get('rows_after', 0):,} rows."],
                    'driver_rows': [], 'visualization': None, 'evidence': {'operation': cleaning_op}, 'action': action, 'download_url': None, 'citations': citations,
                }
        except Exception:
            logger.warning('Cleaning action could not be completed.')
            # fall through to deterministic/fallback assistant

    # 2.2 Data query request
    if intent == 'query' and sql_query:
        try:
            validated_query = validate_readonly_sql(sql_query)
            query_result = _execute_frame(_read_source(item), validated_query)
            
            explain_prompt = f"""You are Pivot Analyst, an expert senior data analyst.
User Question: "{question}"

To answer this question, the following SQLite query was run against the table 'dataset':
```sql
{validated_query}
```

Result returned:
Columns: {query_result['columns']}
Rows: {json.dumps(query_result['rows'][:30], indent=2)}
Total count of matching records: {query_result['count']}

Please summarize these findings and answer the user's question in plain English.
- Be precise and refer to the exact numbers from the query results.
- If the user asks "why" or "what changed", perform a analysis of the query results and explain the cause-and-effect relationship shown in the data.
- Design a chart visualization if a chart would help represent the query result (e.g. trends over time, comparisons of categories).

Respond ONLY with a JSON block in this exact format:
```json
{{
  "answer": "Plain English answer explaining the data and results...",
  "insights": ["Key insight bullet 1", "Key insight bullet 2"], // 1 to 3 items
  "visualization": {{
    "type": "line" | "bar",
    "title": "Descriptive Chart Title",
    "x": "column_name_for_x_axis",
    "y": "column_name_for_y_axis",
    "data": [
      {{"label": "X_value_1", "value": Y_numeric_value_1}},
      ...
    ]
  }} // include only if chart is applicable
}}
```"""
            explain_response = call_gemini(explain_prompt)
            explain_json = extract_json(explain_response)
            
            if explain_json:
                answer = explain_json.get('answer', '')
                insights = explain_json.get('insights', [])
                visualization = explain_json.get('visualization')
                
                capped_rows = query_result['rows'][:10]
                return {
                    'answer': answer,
                    'source': 'pivot-analyst',
                    'intent': 'query',
                    'sql': validated_query,
                    'query_result': {'columns': query_result['columns'], 'rows': capped_rows, 'count': query_result['count']},
                    'rows': capped_rows,
                    'insights': insights,
                    'driver_rows': [],
                    'visualization': visualization,
                    'evidence': {'query': validated_query},
                    'action': None,
                    'download_url': None,
                    'citations': citations,
                }
        except Exception:
            logger.warning('AI query execution could not be completed.')
            # fall through to deterministic/fallback assistant

    # 2.3 General Chat or Fallback (for no API key or execution failure)
    result = answer_question(question, _read_source(item), profile, history=history or [])
    
    # Handle needs_gemini fallback
    if result.get('intent') == 'needs_gemini' and settings.gemini_api_key:
        try:
            # Build dataset context
            schema_info = profile.get('schema', {})
            columns_list = profile.get('columns_list', [])
            data_summary = result.get('evidence', {}).get('data_summary', {})
            dataset_context = json.dumps({
                'dataset_name': item['name'],
                'rows': profile.get('rows', 0),
                'columns': columns_list,
                'numeric_fields': schema_info.get('numeric_columns', []),
                'date_fields': schema_info.get('date_columns', []),
                'quality_score': profile.get('quality_score'),
                'issues': profile.get('issues', []),
                'metrics': profile.get('metrics', {}),
                'sample_values': data_summary.get('sample_values', {}),
            }, default=str)[:8000]

            # Build multi-turn conversation for Gemini
            system_prompt = f'''You are Pivot Analyst, an expert data analyst assistant. You are analyzing a dataset called "{item['name']}" with {profile.get('rows', 0):,} rows and {profile.get('columns', 0)} columns.

RULES:
- Answer ONLY in plain English. Never output SQL queries.
- Reference actual data from the conversation history when available.
- If a user asks "why" something happened, analyze the data patterns and provide plausible explanations.
- Be specific with numbers. Don't make up numbers.
- Keep answers concise but insightful — like a real senior data analyst would respond.
- Format your response naturally with line breaks for readability.

Dataset context:
{dataset_context}'''

            gemini_contents = [system_prompt]
            for entry in (history or [])[-10:]:
                role = entry.get('role', '')
                text_content = entry.get('text', '')
                if text_content and role in ('user', 'assistant'):
                    gemini_contents.append(f"{'User' if role == 'user' else 'Analyst'}: {text_content}")
            gemini_contents.append(f"User: {question}")

            res_text = call_gemini('\n\n'.join(gemini_contents))
            if res_text:
                result['answer'] = res_text.strip()
                result['intent'] = 'gemini-explanation'
        except Exception:
            available = result.get('available_fields', '')
            result['answer'] = f"I can investigate this dataset but couldn't map that request to a reliable calculation. Available fields include {available}."
            result['intent'] = 'clarification'

    rows = result.get('rows') or []
    display_rows = rows[:10]
    columns = list(display_rows[0].keys()) if display_rows else []
    query_result = {'columns': columns, 'rows': display_rows, 'count': len(rows)} if display_rows else None
    
    return {
        'answer': result['answer'],
        'source': 'pivot-analyst',
        'intent': result.get('intent'),
        'sql': result.get('sql'),
        'query_result': query_result,
        'rows': display_rows,
        'insights': result.get('insights', []),
        'driver_rows': result.get('driver_rows', []),
        'visualization': result.get('visualization'),
        'evidence': result.get('evidence', {}),
        'action': None,
        'download_url': None,
        'citations': citations,
    }


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
    path = _save_text(item, content, safe_title, f'.{suffix}')
    report_id = add_report(dataset_id, body.title or 'Pivot report', format_name, path)
    return {'id': report_id, 'title': body.title or 'Pivot report', 'format': format_name, 'download_url': f'/api/datasets/{dataset_id}/reports/{report_id}/download'}


@app.get('/api/datasets/{dataset_id}/reports/{report_id}/download')
def download_report(dataset_id: str, report_id: str):
    item = _dataset_or_404(dataset_id)
    report = next((report for report in reports_for(dataset_id) if report['id'] == report_id), None)
    if not report:
        raise HTTPException(404, 'Report not found.')
    path = report['path']
    return StreamingResponse(get_storage().stream(path), headers={'Content-Disposition': f'attachment; filename="{Path(path).name}"'})


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
