from __future__ import annotations

import re
from io import BytesIO

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


def chunks(text: str, size: int = 900, overlap: int = 150) -> list[str]:
    normalized_text = re.sub(r'\s+', ' ', text).strip()
    step = size - overlap

    if not normalized_text or step <= 0:
        return []

    chunks = []
    for start in range(0, len(normalized_text), step):
        chunk = normalized_text[start:start + size].strip()
        if chunk:
            chunks.append(chunk)

    return chunks


def extract(filename: str, raw: bytes) -> list[str]:
    filename_lower = filename.lower()

    if filename_lower.endswith('.pdf'):
        from pypdf import PdfReader

        document = PdfReader(BytesIO(raw))
        pages = [page.extract_text() or '' for page in document.pages]
        return chunks('\n'.join(pages))

    if filename_lower.endswith(('.json', '.md', '.txt')):
        document_text = raw.decode('utf-8', errors='ignore')
        return chunks(document_text)

    return []


def retrieve(question: str, records: list[dict], limit: int = 5) -> list[dict]:
    if not records:
        return []

    corpus = [record['content'] for record in records]
    vectorizer = TfidfVectorizer(stop_words='english', max_features=7000)
    matrix = vectorizer.fit_transform(corpus + [question])
    scores = cosine_similarity(matrix[-1], matrix[:-1]).flatten()
    ranked_indexes = scores.argsort()[::-1][:limit]

    matches = []
    for index in ranked_indexes:
        if scores[index] <= 0:
            continue

        matches.append({
            'source': records[index]['source'],
            'content': corpus[index],
            'score': round(float(scores[index]), 3),
        })

    return matches
