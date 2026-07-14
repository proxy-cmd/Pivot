from __future__ import annotations

import io
import json
import asyncio
from pathlib import Path
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse

from .analytics import forecast, profile_frame, scenario
from .config import get_settings
from .models import ChatRequest, ScenarioRequest
from .models import TransformRequest
from .rag import extract, retrieve
from .store import add_chunks, add_version, chunks_for, create_dataset, events_for, finish_dataset, get_dataset

app = FastAPI(title='Verdant Analytics API', version='1.0.0')
settings = get_settings()
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins.split(','), allow_credentials=True, allow_methods=['*'], allow_headers=['*'])


@app.get('/health')
def health():
    return {'status': 'ok', 'service': 'verdant-analytics'}


@app.post('/api/datasets')
async def profile(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(400, 'File name is required.')
    data = await file.read()
    suffix = Path(file.filename).suffix.lower()
    dataset_id = create_dataset(file.filename, suffix, data)
    try:
        import pandas as pd
        source = io.BytesIO(data)
        if suffix in ('.xlsx', '.xls'):
            frame = pd.read_excel(source)
        elif suffix == '.json':
            frame = pd.read_json(source)
        elif suffix == '.parquet':
            frame = pd.read_parquet(source)
        else:
            frame = pd.read_csv(source)
    except Exception as error:
        raise HTTPException(422, f'Could not read file: {error}') from error
    if frame.empty:
        raise HTTPException(422, 'The uploaded file contains no records.')
    result = profile_frame(frame, file.filename)
    result['dataset_id'] = dataset_id
    result['recommendations'] = [{'operation': 'trim_text', 'label': 'Trim whitespace', 'reason': 'Safe cleanup for text fields; requires approval.'}, {'operation': 'remove_duplicates', 'label': 'Remove exact duplicates', 'reason': 'Preserves source and creates a reversible version.'}, {'operation': 'normalize_columns', 'label': 'Normalize column names', 'reason': 'Improves reliable downstream mapping.'}]
    context = [f"Dataset: {file.filename}", f"Role: {result['role']}", f"Rows: {result['rows']}", f"Columns: {', '.join(frame.columns.astype(str).tolist())}", frame.head(25).to_csv(index=False)]
    add_chunks(dataset_id, file.filename, context + extract(file.filename, data))
    finish_dataset(dataset_id, result)
    return result


@app.post('/api/profile')
async def legacy_profile(file: UploadFile = File(...)):
    return await profile(file)


@app.get('/api/datasets/{dataset_id}')
def dataset(dataset_id: str):
    item = get_dataset(dataset_id)
    if not item: raise HTTPException(404, 'Dataset session not found.')
    return item


@app.get('/api/datasets/{dataset_id}/events')
async def stream_events(dataset_id: str):
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
    if not get_dataset(dataset_id): raise HTTPException(404, 'Dataset session not found.')
    add_version(dataset_id, body.operation, body.note or 'Awaiting explicit user approval before any source data is changed.')
    return {'ok': True, 'message': 'Transformation plan recorded in lineage. Source data remains unchanged.'}


@app.post('/api/forecast')
def create_forecast(values: list[float]):
    return forecast(values)


@app.post('/api/scenario')
def run_scenario(body: ScenarioRequest):
    return scenario(body.price_change, body.marketing_change, body.cost_change, body.baseline_revenue)


@app.post('/api/chat')
def chat(body: ChatRequest):
    retrieved = retrieve(body.question, chunks_for(body.dataset_id)) if body.dataset_id else []
    context = json.dumps({'dashboard': body.context, 'retrieved_context': retrieved}, default=str)[:12000]
    if settings.gemini_api_key:
        try:
            from google import genai
            client = genai.Client(api_key=settings.gemini_api_key)
            prompt = f'''You are Pivot, a careful senior data analyst. Answer only from supplied context. State uncertainty clearly. Cite source names in square brackets when using retrieved context. Never claim a transformation was applied unless lineage says so.\n\nContext: {context}\n\nQuestion: {body.question}'''
            response = client.models.generate_content(model='gemini-2.0-flash', contents=prompt)
            return {'answer': response.text, 'source': 'gemini-rag', 'citations': [{'source': item['source'], 'score': item['score']} for item in retrieved]}
        except Exception:
            pass
    if retrieved:
        return {'answer': f"I found relevant material in {', '.join(sorted(set(item['source'] for item in retrieved)))}. Configure Gemini in backend/.env for a natural-language answer grounded in these retrieved passages.", 'source': 'local-rag', 'citations': [{'source': item['source'], 'score': item['score']} for item in retrieved]}
    return {'answer': 'Revenue is trending up, while fulfillment cost growth is the primary margin risk. Upload a dataset or document and configure Gemini in backend/.env for grounded RAG answers.', 'source': 'rule-based', 'citations': []}


public = Path('public')
if public.exists():
    app.mount('/', StaticFiles(directory=public, html=True), name='web')
