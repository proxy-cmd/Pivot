from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from uuid import uuid4
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .assistant import answer_question
from .analytics import prepare_frame
from .autopilot import briefing_markdown, build_report, clean_frame, explore, plan_prompt
from .core.config import get_settings
from .database import get_engine
from .gemini import generate as call_gemini, parse_json_object as extract_json
from .dataset_io import (
    available_analyses,
    profile_payload,
    read_dataset_source,
    read_file,
    save_frame,
    temporary_path,
    validate_upload_name,
)
from .dataset_sql import deterministic_query, execute_query, generate_query
from .auth import authenticate_request, current_user_id
from .auth_routes import router as auth_router
from .api.deps import dataset_or_404
from .api.routes.analytics import router as analytics_router
from .api.routes.sql import router as sql_router
from .schemas.requests import ChatRequest, ReportRequest, TransformRequest
from .rag import extract, retrieve
from .core.security import validate_readonly_sql
from .services.transformations import TransformationError, approve as approve_preview, preview as preview_operation, reject as reject_preview
from .services.reports import create as create_dataset_report
from .storage import get_storage
from .store import (
    add_chunks, add_report, add_version, chunks_for, create_dataset,
    event as record_event, events_for, finish_dataset, reports_for, activate_dataset_version,
)

settings = get_settings()
logger = logging.getLogger(__name__)

# Keep the local name while routes are incrementally moved into ``api/routes``.
_dataset_or_404 = dataset_or_404


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
app.include_router(analytics_router)
app.include_router(sql_router)

_requests: dict[str, deque[float]] = defaultdict(deque)
RATE_LIMITS = {
    '/api/auth/google/login': (10, 60),
    '/api/auth/refresh': (30, 60),
    '/api/chat': (40, 60),
    '/api/datasets': (12, 300),
}
PUBLIC_PATHS = {'/health', '/docs', '/openapi.json', '/redoc'}
MUTATING_METHODS = {'POST', 'PUT', 'PATCH', 'DELETE'}


def _is_rate_limited(request: Request) -> bool:
    rule = RATE_LIMITS.get(request.url.path)
    if not rule:
        return False

    limit, window = rule
    key = rate_limit_key(request)
    now = time.monotonic()
    entries = _requests[key]

    remove_expired_requests(entries, now, window)
    if len(entries) >= limit:
        return True

    entries.append(now)
    return False


def rate_limit_key(request: Request) -> str:
    client_host = request.client.host if request.client else 'unknown'
    return f'{request.url.path}:{client_host}'


def remove_expired_requests(entries: deque[float], now: float, window: int) -> None:
    while entries and entries[0] <= now - window:
        entries.popleft()


def _trusted_origin(request: Request) -> bool:
    origin = request.headers.get('origin')
    if not origin:
        return True
    return origin.rstrip('/') in {value.rstrip('/') for value in cors_origins}


@app.middleware('http')
async def authentication_middleware(request: Request, call_next):
    path = request.url.path
    if _is_rate_limited(request):
        return JSONResponse({'detail': 'Too many requests. Please try again shortly.'}, status_code=429, headers={'Retry-After': '60'})

    if request_is_public(request):
        return await call_next(request)

    if not path.startswith('/api/'):
        return await call_next(request)

    if request_requires_origin_check(request) and not _trusted_origin(request):
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


def request_is_public(request: Request) -> bool:
    return request.method == 'OPTIONS' or request.url.path in PUBLIC_PATHS or request.url.path.startswith('/api/auth/')


def request_requires_origin_check(request: Request) -> bool:
    is_mutating_request = request.method in MUTATING_METHODS
    uses_access_cookie = bool(request.cookies.get('pivot_access'))
    return is_mutating_request and uses_access_cookie


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
async def upload_dataset(file: UploadFile = File(...)):
    filename, suffix = upload_details(file)
    dataset_id = uuid4().hex
    frame, source_key = await store_upload(file, filename, suffix, dataset_id)
    profile = profile_payload(frame, filename, dataset_id)

    create_dataset(filename, source_key, dataset_id)
    add_chunks(dataset_id, filename, dataset_context(filename, frame, profile))
    finish_dataset(dataset_id, profile)

    return profile


@app.post('/api/profile')
async def legacy_profile(file: UploadFile = File(...)):
    return await upload_dataset(file)


def upload_details(file: UploadFile) -> tuple[str, str]:
    if not file.filename:
        raise HTTPException(400, 'File name is required.')

    validate_upload_name(file.filename)
    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(415, 'Supported files are CSV, Excel, JSON, and Parquet.')
    if file.content_type not in ALLOWED_UPLOAD_TYPES:
        raise HTTPException(415, 'The uploaded content type is not supported.')

    return file.filename, suffix


async def store_upload(file: UploadFile, filename: str, suffix: str, dataset_id: str) -> tuple[pd.DataFrame, str]:
    with temporary_path(suffix) as path:
        await write_upload(file, path)
        frame = load_uploaded_frame(path, suffix)
        validate_uploaded_frame(frame)

        owner_id = current_user_id.get()
        source_key = get_storage().key(owner_id, dataset_id, 'source', suffix)
        get_storage().upload_file(path, source_key)

    return frame, source_key


async def write_upload(file: UploadFile, path: Path) -> None:
    size = 0
    with path.open('wb') as handle:
        while chunk := await file.read(64 * 1024):
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                maximum_megabytes = MAX_UPLOAD_BYTES // 1024 // 1024
                raise HTTPException(413, f'Files must be {maximum_megabytes}MB or smaller.')
            handle.write(chunk)


def load_uploaded_frame(path: Path, suffix: str) -> pd.DataFrame:
    try:
        return prepare_frame(read_file(path, suffix))
    except Exception as error:
        raise HTTPException(422, f'Could not read file: {error}') from error


def validate_uploaded_frame(frame: pd.DataFrame) -> None:
    if frame.empty:
        raise HTTPException(422, 'The uploaded file contains no records.')
    if len(frame) > MAX_UPLOAD_ROWS:
        raise HTTPException(413, f'Datasets must contain {MAX_UPLOAD_ROWS:,} rows or fewer.')


def dataset_context(filename: str, frame: pd.DataFrame, profile: dict[str, Any]) -> list[str]:
    return [
        f'Dataset: {filename}',
        f'Role: {profile["role"]}',
        f'Rows: {profile["rows"]}',
        f'Columns: {", ".join(frame.columns.astype(str).tolist())}',
        frame.head(25).to_csv(index=False),
    ]


@app.get('/api/datasets/{dataset_id}')
def dataset(dataset_id: str):
    item = _dataset_or_404(dataset_id)
    item['events'] = events_for(dataset_id)
    item['reports'] = reports_for(dataset_id)
    return item


@app.get('/api/datasets/{dataset_id}/overview')
def overview(dataset_id: str):
    item = _dataset_or_404(dataset_id)
    return overview_payload(read_dataset_source(item), item['profile'] or {})


@app.get('/api/datasets/{dataset_id}/analyses')
def analyses(dataset_id: str):
    item = dataset_or_404(dataset_id)
    return {'analyses': available_analyses(read_dataset_source(item), item['profile'] or {})}


@app.post('/api/datasets/{dataset_id}/context')
async def add_dataset_context(dataset_id: str, file: UploadFile = File(...)):
    """Attach a business glossary or data dictionary to a dataset's RAG context."""
    _dataset_or_404(dataset_id)
    if not file.filename:
        raise HTTPException(400, 'A context file name is required.')
    validate_upload_name(file.filename)
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
    source = read_dataset_source(item)
    cleaned, steps = clean_frame(source)
    cleaned_profile = profile_payload(cleaned, item['name'], dataset_id)
    facts = explore(cleaned, cleaned_profile)
    plan = None
    if settings.gemini_api_key:
        plan = extract_json(call_gemini(plan_prompt(cleaned_profile, facts)) or '')
    report = build_report(cleaned, cleaned_profile, steps, plan, facts)

    version_number = len(item['versions'])
    output = save_frame(item, cleaned, f'version-{version_number}-autopilot')
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
    briefing_path = save_text(item, briefing, 'auto-pilot-briefing', '.md')
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
    try:
        return preview_operation(_dataset_or_404(dataset_id), operation)
    except TransformationError as error:
        raise HTTPException(422, str(error)) from error


@app.post('/api/datasets/{dataset_id}/transformations/{transformation_id}/approve')
def approve_transformation(dataset_id: str, transformation_id: str):
    try:
        return approve_preview(_dataset_or_404(dataset_id), transformation_id)
    except TransformationError as error:
        raise HTTPException(404, str(error)) from error


@app.post('/api/datasets/{dataset_id}/versions/{number}/activate')
def activate_version(dataset_id: str, number: int):
    item = _dataset_or_404(dataset_id)
    versions = [version for version in item['versions'] if version['number'] == number]
    if not versions:
        raise HTTPException(404, 'Version not found.')
    if number == 0:
        path = item['source_path']
        profile = profile_payload(read_dataset_source({**item, 'active_path': item['source_path']}), item['name'], dataset_id)
    else:
        detail = json.loads(versions[0]['detail'])
        path = detail['output']
        profile = detail.get('profile') or profile_payload(read_dataset_source({**item, 'active_path': path}), item['name'], dataset_id)
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
        before_frame = read_dataset_source({**item, 'active_path': before})
        after_frame = read_dataset_source({**item, 'active_path': after})
    except HTTPException:
        raise HTTPException(404, 'One of the requested version outputs is unavailable.')
    return {'from_version': from_version, 'to_version': to_version, 'rows_before': len(before_frame), 'rows_after': len(after_frame), 'columns_before': before_frame.columns.tolist(), 'columns_after': after_frame.columns.tolist(), 'added_columns': [column for column in after_frame.columns if column not in before_frame.columns], 'removed_columns': [column for column in before_frame.columns if column not in after_frame.columns]}


@app.post('/api/datasets/{dataset_id}/transformations/{transformation_id}/reject')
def reject_transformation(dataset_id: str, transformation_id: str):
    try:
        return reject_preview(_dataset_or_404(dataset_id)['id'], transformation_id)
    except TransformationError as error:
        raise HTTPException(404, str(error)) from error


@app.post('/api/datasets/{dataset_id}/transformations/{operation}/execute')
def execute_transformation_compat(dataset_id: str, operation: str):
    preview = preview_transformation(dataset_id, operation)
    return approve_transformation(dataset_id, preview['id'])


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
    query = deterministic_query(body.question, item) or generate_query(body.question, item)
    evidence: dict[str, Any] = {'profile': {'rows': profile.get('rows'), 'columns': profile.get('columns_list'), 'quality_score': profile.get('quality_score'), 'issues': profile.get('issues'), 'metrics': profile.get('metrics')}, 'retrieved_context': retrieved}
    if query:
        try:
            query = validate_readonly_sql(query)
            evidence['query'] = query
            evidence['query_result'] = execute_query(read_dataset_source(item), query)
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
        prompt = f'''You are Pivot, a senior data analyst. Answer the question only from the evidence below. Do not invent facts, business labels, trends, or recommendations. If the evidence is insufficient, say exactly that. Include the relevant numbers and explain the query evidence in plain language. Never claim a transformation occurred unless the evidence says so.\n\nEvidence:\n{context}\n\nQuestion: {body.question}'''
        response = call_gemini(prompt)
        if response:
            return {'answer': response, 'source': 'gemini-analyst', 'sql': query, 'query_result': evidence.get('query_result'), 'citations': sources}
    query_result = evidence.get('query_result') or {}
    if query_result.get('count', 0) or retrieved or profile.get('issues'):
        rows = query_result.get('rows') or []
        sample = '; '.join(', '.join(f'{key}={value}' for key, value in row.items()) for row in rows[:3])
        detail = f" The first evidence rows are: {sample}." if sample else ''
        return {'answer': f"I found evidence in {item['name']} and returned {query_result.get('count', 0)} matching rows.{detail}", 'source': 'deterministic-evidence', 'sql': query, 'query_result': query_result, 'citations': sources}
    return {'answer': f"Hi — I’m connected to {item['name']}. I found {profile.get('rows', 0)} rows and {profile.get('columns', 0)} detected fields. Ask me about trends, quality, categories, or values and I’ll investigate the source.", 'source': 'dataset-aware', 'sql': query, 'citations': sources}


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
            query_result = execute_query(read_dataset_source(item), validated_query)
            
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
    result = answer_question(question, read_dataset_source(item), profile, history=history or [])
    
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
    try:
        return create_dataset_report(item, body.title, body.format)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


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
