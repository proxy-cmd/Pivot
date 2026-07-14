from typing import Any
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    context: dict[str, Any] = Field(default_factory=dict)
    dataset_id: str | None = None


class TransformRequest(BaseModel):
    operation: str = Field(pattern='^(trim_text|remove_duplicates|normalize_columns|parse_dates)$')
    note: str = Field(default='', max_length=500)


class ScenarioRequest(BaseModel):
    price_change: float = Field(default=0, ge=-50, le=100)
    marketing_change: float = Field(default=0, ge=-50, le=200)
    cost_change: float = Field(default=0, ge=-50, le=100)
    baseline_revenue: float = Field(default=238000, gt=0)
