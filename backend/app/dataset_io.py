"""Dataset file, storage, and profile operations shared by API workflows.

This module deliberately owns dataframe I/O and profile-shaped responses.  It does
not know about routes, database records, or transformation approval workflows.
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path
from tempfile import mkstemp
from typing import Any, Iterator

import pandas as pd
from fastapi import HTTPException

from .analytics import _numeric_series, prepare_frame, profile_frame
from .storage import get_storage


def validate_upload_name(filename: str) -> None:
    if len(filename) > 255 or Path(filename).name != filename or any(ord(char) < 32 for char in filename):
        raise HTTPException(400, 'Invalid file name.')


def read_file(source: Path, suffix: str) -> pd.DataFrame:
    if suffix in ('.xlsx', '.xls'):
        return pd.read_excel(source)
    if suffix == '.json':
        return pd.read_json(source)
    if suffix == '.parquet':
        return pd.read_parquet(source)
    return pd.read_csv(source)


@contextmanager
def temporary_path(suffix: str) -> Iterator[Path]:
    descriptor, name = mkstemp(suffix=suffix)
    os.close(descriptor)
    path = Path(name)
    try:
        yield path
    finally:
        path.unlink(missing_ok=True)


def read_dataset_source(item: dict[str, Any]) -> pd.DataFrame:
    try:
        with get_storage().local_file(item.get('active_path') or item['source_path']) as path:
            if not path.exists():
                raise FileNotFoundError(path)
            frame = read_file(path, path.suffix.lower())
    except Exception as error:
        raise HTTPException(422, f'Could not read the preserved source: {error}') from error

    frame = prepare_frame(frame)
    for column in (item.get('profile') or {}).get('schema', {}).get('numeric_columns', []):
        if column in frame.columns:
            frame[column] = _numeric_series(frame, column)
    return frame


def save_frame(item: dict[str, Any], frame: pd.DataFrame, name: str) -> str:
    key = get_storage().key(item['owner_user_id'], item['id'], name, '.csv')
    with temporary_path('.csv') as path:
        frame.to_csv(path, index=False)
        get_storage().upload_file(path, key)
    return key


def save_text(item: dict[str, Any], text: str, name: str, suffix: str) -> str:
    key = get_storage().key(item['owner_user_id'], item['id'], name, suffix)
    with temporary_path(suffix) as path:
        path.write_text(text, encoding='utf-8')
        get_storage().upload_file(path, key)
    return key


def profile_payload(frame: pd.DataFrame, filename: str, dataset_id: str) -> dict[str, Any]:
    result = profile_frame(frame, filename)
    result['dataset_id'] = dataset_id
    result['preview'] = json.loads(frame.head(8).fillna('').to_json(orient='records', date_format='iso'))
    result['columns_list'] = [str(column) for column in frame.columns]
    issue_operations = {
        'missing_values': ('fill_missing', 'Fill missing values'),
        'duplicate_records': ('remove_duplicates', 'Remove exact duplicates'),
        'whitespace': ('trim_text', 'Trim text fields'),
        'invalid_dates': ('parse_dates', 'Parse detected date fields'),
        'outliers': ('remove_outliers', 'Review numeric outliers'),
        'negative_values': ('remove_outliers', 'Review negative and extreme numeric values'),
    }
    recommendations = []
    for issue in result.get('issues', []):
        operation, label = issue_operations.get(issue['type'], ('normalize_columns', 'Normalize column names'))
        if not any(item['operation'] == operation for item in recommendations):
            recommendations.append({'operation': operation, 'label': label, 'reason': issue['fix']})
    result['recommendations'] = recommendations
    return result


def overview_payload(frame: pd.DataFrame, profile: dict[str, Any]) -> dict[str, Any]:
    schema = profile.get('schema', {})
    numeric = schema.get('numeric_columns', [])
    dates = schema.get('date_columns', [])
    cards = [
        {'label': 'Rows', 'value': profile.get('rows', 0), 'kind': 'count'},
        {'label': 'Columns', 'value': profile.get('columns', 0), 'kind': 'count'},
        {'label': 'Quality score', 'value': profile.get('quality_score', 0), 'suffix': '/100', 'kind': 'quality'},
    ]
    for column in numeric[:3]:
        values = _numeric_series(frame, column).dropna()
        if len(values):
            cards.append({'label': column.replace('_', ' ').title(), 'value': round(float(values.sum()), 2), 'kind': 'metric', 'column': column})
    chart: list[dict[str, Any]] = []
    if dates and numeric:
        date_column, value_column = dates[0], numeric[0]
        dates_series = pd.to_datetime(frame[date_column], errors='coerce')
        values = _numeric_series(frame, value_column)
        grouped = pd.DataFrame({'period': dates_series.dt.to_period('M').astype('string'), 'value': values}).dropna()
        if not grouped.empty:
            chart = [{'period': str(row['period']), 'value': round(float(row['value']), 2)} for _, row in grouped.groupby('period', as_index=False)['value'].sum().tail(24).iterrows()]
    breakdown = []
    dimensions = [column for column in frame.columns if column not in numeric and column not in dates]
    if dimensions:
        counts = frame[dimensions[0]].fillna('(blank)').astype(str).value_counts().head(8)
        breakdown = [{'label': str(label), 'value': int(value)} for label, value in counts.items()]
    return {'cards': cards, 'trend': chart, 'breakdown': breakdown, 'trend_columns': {'date': dates[0] if dates else None, 'value': numeric[0] if numeric else None}}


def available_analyses(frame: pd.DataFrame, profile: dict[str, Any]) -> list[dict[str, Any]]:
    schema = profile.get('schema', {})
    analyses = []
    for column in schema.get('numeric_columns', []):
        label = column.replace('_', ' ')
        analyses.append({'id': f'trend:{column}', 'kind': 'trend', 'title': f'Trend of {label}', 'description': f'Inspect how {label} changes over time.', 'column': column, 'enabled': bool(schema.get('date_columns'))})
        analyses.append({'id': f'distribution:{column}', 'kind': 'distribution', 'title': f'Distribution of {label}', 'description': f'Summarize the spread, center, and extremes of {label}.', 'column': column, 'enabled': True})
    dimensions = [column for column in frame.columns if column not in schema.get('numeric_columns', []) and column not in schema.get('date_columns', [])]
    for column in dimensions[:8]:
        label = column.replace('_', ' ')
        analyses.append({'id': f'breakdown:{column}', 'kind': 'breakdown', 'title': f'Breakdown by {label}', 'description': f'Compare the most common values in {label}.', 'column': column, 'enabled': True})
    analyses.append({'id': 'quality', 'kind': 'quality', 'title': 'Data quality review', 'description': 'Review completeness, duplicates, and detected quality risks.', 'enabled': True})
    return analyses
