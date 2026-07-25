from __future__ import annotations

import re
from io import BytesIO

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


def chunks(text: str, size: int = 900, overlap: int = 150) -> list[str]:
    text = re.sub(r'\s+', ' ', text).strip()
    return [text[start:start + size] for start in range(0, len(text), size - overlap) if text[start:start + size].strip()]


def extract(filename: str, raw: bytes) -> list[str]:
    lower = filename.lower()
    if lower.endswith('.pdf'):
        from pypdf import PdfReader
        text = '\n'.join(page.extract_text() or '' for page in PdfReader(BytesIO(raw)).pages)
        return chunks(text)
    if lower.endswith(('.json', '.md', '.txt')):
        return chunks(raw.decode('utf-8', errors='ignore'))
    return []


def retrieve(question: str, records: list[dict], limit: int = 5) -> list[dict]:
    if not records: return []
    corpus = [record['content'] for record in records]
    vectorizer = TfidfVectorizer(stop_words='english', max_features=7000)
    matrix = vectorizer.fit_transform(corpus + [question])
    scores = cosine_similarity(matrix[-1], matrix[:-1]).flatten()
    best = scores.argsort()[::-1][:limit]
    return [{'source': records[index]['source'], 'content': corpus[index], 'score': round(float(scores[index]), 3)} for index in best if scores[index] > 0]
