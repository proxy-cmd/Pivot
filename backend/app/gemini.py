"""Minimal Gemini provider boundary used by Pivot's AI workflows."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from .config import get_settings

logger = logging.getLogger(__name__)


def generate(prompt: str) -> str | None:
    settings = get_settings()
    if not settings.gemini_api_key:
        return None
    try:
        from google import genai

        response = genai.Client(api_key=settings.gemini_api_key).models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
        )
        return response.text
    except Exception:
        logger.warning('Gemini call failed.')
        return None


def parse_json_object(text: str | None) -> dict[str, Any] | None:
    """Accept either a raw or fenced JSON object from the model."""
    if not text:
        return None
    try:
        fenced = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
        if fenced:
            return json.loads(fenced.group(1).strip())
        cleaned = text.strip()
        if cleaned.startswith('{') and cleaned.endswith('}'):
            return json.loads(cleaned)
        start, end = cleaned.find('{'), cleaned.rfind('}')
        if start != -1 and end != -1:
            return json.loads(cleaned[start:end + 1])
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return None
