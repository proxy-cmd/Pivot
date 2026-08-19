"""Dataset analysis and forecasting HTTP endpoints."""

from fastapi import APIRouter, HTTPException

from ...analytics import forecast, scenario
from ...dataset_analysis import run_analysis
from ...dataset_io import read_dataset_source
from ...schemas.requests import AnalysisRequest, ScenarioRequest
from ..deps import dataset_or_404

router = APIRouter()


@router.post('/api/datasets/{dataset_id}/analyses/run')
def run_dataset_analysis(dataset_id: str, body: AnalysisRequest):
    dataset = dataset_or_404(dataset_id)
    try:
        return run_analysis(read_dataset_source(dataset), dataset['profile'] or {}, body.kind, body.column)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@router.post('/api/forecast')
def create_forecast(values: list[float]):
    return forecast(values)


@router.post('/api/scenario')
def run_scenario(body: ScenarioRequest):
    return scenario(body.price_change, body.marketing_change, body.cost_change, body.baseline_revenue)
