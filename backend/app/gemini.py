"""Minimal Gemini provider boundary used by Pivot's AI workflows."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from .core.config import get_settings

logger = logging.getLogger(__name__)


def generate(prompt: str) -> str | None:
    settings = get_settings()
    if not settings.gemini_api_key:
        return None

    try:
        return generate_content(settings.gemini_api_key, settings.gemini_model, prompt)
    except Exception as error:
        logger.warning('Gemini call failed error=%s', type(error).__name__)
        return None


def generate_content(api_key: str, model: str, prompt: str) -> str | None:
    from google import genai

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(model=model, contents=prompt)
    return response.text


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
        start_index = cleaned.find('{')
        end_index = cleaned.rfind('}')
        if start_index != -1 and end_index != -1:
            return json.loads(cleaned[start_index:end_index + 1])
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return None
