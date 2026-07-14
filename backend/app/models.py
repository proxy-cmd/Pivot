from typing import Any
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    context: dict[str, Any] = Field(default_factory=dict)
    dataset_id: str | None = None


class TransformRequest(BaseModel):
    operation: str = Field(pattern='^(trim_text|remove_duplicates|normalize_columns|parse_dates)$')
    note: str = Field(default='', max_length=500)


class SqlRequest(BaseModel):
    dataset_id: str
    query: str = Field(min_length=8, max_length=5000)


class SqlAskRequest(BaseModel):
    dataset_id: str
    question: str = Field(min_length=4, max_length=1000)


class ScenarioRequest(BaseModel):
    price_change: float = Field(default=0, ge=-50, le=100)
    marketing_change: float = Field(default=0, ge=-50, le=200)
    cost_change: float = Field(default=0, ge=-50, le=100)
    baseline_revenue: float = Field(gt=0)


class AnalysisRequest(BaseModel):
    kind: str = Field(pattern='^(trend|distribution|breakdown|quality)$')
    column: str | None = Field(default=None, max_length=200)


class ReportRequest(BaseModel):
    title: str = Field(default='Pivot report', min_length=1, max_length=120)
    format: str = Field(default='md', pattern='^(md|html|json)$')
