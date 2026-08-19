"""Read-only SQL HTTP endpoints."""

from fastapi import APIRouter, HTTPException

from ...core.security import validate_readonly_sql
from ...dataset_io import read_dataset_source
from ...dataset_sql import deterministic_query, execute_query, generate_query
from ...schemas.requests import SqlAskRequest, SqlRequest
from ..deps import dataset_or_404

router = APIRouter()


@router.post('/api/sql/validate')
def validate_sql(body: SqlRequest):
    dataset_or_404(body.dataset_id)
    try:
        query = validate_readonly_sql(body.query)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    return {'safe': True, 'query': query, 'explanation': 'Read-only query accepted for the active dataset.'}


@router.post('/api/sql/execute')
def execute_sql(body: SqlRequest):
    dataset = dataset_or_404(body.dataset_id)
    try:
        query = validate_readonly_sql(body.query)
        return execute_query(read_dataset_source(dataset), query)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        raise HTTPException(422, f'Could not run this query: {error}') from error


@router.post('/api/sql/generate')
def generate_sql(body: SqlAskRequest):
    dataset = dataset_or_404(body.dataset_id)
    query = deterministic_query(body.question, dataset) or generate_query(body.question, dataset)
    if not query:
        raise HTTPException(422, 'I could not find enough schema evidence to generate a query.')
    try:
        query = validate_readonly_sql(query)
        result = execute_query(read_dataset_source(dataset), query)
    except Exception as error:
        raise HTTPException(422, f'I generated a query that could not be safely executed: {error}') from error
    return result | {'sql': query, 'explanation': 'The query was generated from the detected schema, validated, and executed against the uploaded dataset.'}
