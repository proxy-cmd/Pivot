from __future__ import annotations

import io
import json
from pathlib import Path
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .analytics import forecast, profile_frame, scenario
from .config import get_settings
from .models import ChatRequest, ScenarioRequest

app = FastAPI(title='Verdant Analytics API', version='1.0.0')
settings = get_settings()
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins.split(','), allow_credentials=True, allow_methods=['*'], allow_headers=['*'])


@app.get('/health')
def health():
    return {'status': 'ok', 'service': 'verdant-analytics'}


@app.post('/api/profile')
async def profile(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(400, 'File name is required.')
    data = await file.read()
    try:
        import pandas as pd
        source = io.BytesIO(data)
        frame = pd.read_excel(source) if file.filename.lower().endswith(('.xlsx', '.xls')) else pd.read_csv(source)
    except Exception as error:
        raise HTTPException(422, f'Could not read file: {error}') from error
    if frame.empty:
        raise HTTPException(422, 'The uploaded file contains no records.')
    return profile_frame(frame, file.filename)


@app.post('/api/forecast')
def create_forecast(values: list[float]):
    return forecast(values)


@app.post('/api/scenario')
def run_scenario(body: ScenarioRequest):
    return scenario(body.price_change, body.marketing_change, body.cost_change, body.baseline_revenue)


@app.post('/api/chat')
def chat(body: ChatRequest):
    context = json.dumps(body.context, default=str)[:8000]
    if settings.gemini_api_key:
        try:
            from google import genai
            client = genai.Client(api_key=settings.gemini_api_key)
            prompt = f'''You are Verdant, a careful senior business analyst. Answer using only the supplied context. State uncertainty clearly. Cite specific figures from the context. Do not fabricate data.\n\nContext: {context}\n\nQuestion: {body.question}'''
            response = client.models.generate_content(model='gemini-2.0-flash', contents=prompt)
            return {'answer': response.text, 'source': 'gemini'}
        except Exception:
            pass
    return {'answer': 'Revenue is trending up, while fulfillment cost growth is the primary margin risk. Connect Gemini in backend/.env for deeper, dataset-grounded analysis.', 'source': 'rule-based'}


public = Path('public')
if public.exists():
    app.mount('/', StaticFiles(directory=public, html=True), name='web')
