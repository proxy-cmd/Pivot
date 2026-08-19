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

ISSUE_OPERATIONS = {
    'missing_values': ('fill_missing', 'Fill missing values'),
    'duplicate_records': ('remove_duplicates', 'Remove exact duplicates'),
    'whitespace': ('trim_text', 'Trim text fields'),
    'invalid_dates': ('parse_dates', 'Parse detected date fields'),
    'outliers': ('remove_outliers', 'Review numeric outliers'),
    'negative_values': ('remove_outliers', 'Review negative and extreme numeric values'),
}


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
    profile = profile_frame(frame, filename)
    profile['dataset_id'] = dataset_id
    profile['preview'] = frame_preview(frame)
    profile['columns_list'] = [str(column) for column in frame.columns]
    profile['recommendations'] = transformation_recommendations(profile['issues'])
    return profile


def frame_preview(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return json.loads(frame.head(8).fillna('').to_json(orient='records', date_format='iso'))


def transformation_recommendations(issues: list[dict[str, Any]]) -> list[dict[str, str]]:
    recommendations = []
    for issue in issues:
        recommendation = issue_recommendation(issue)
        already_recommended = any(item['operation'] == recommendation['operation'] for item in recommendations)
        if not already_recommended:
            recommendations.append(recommendation)
    return recommendations


def issue_recommendation(issue: dict[str, Any]) -> dict[str, str]:
    operation, label = ISSUE_OPERATIONS.get(issue['type'], ('normalize_columns', 'Normalize column names'))
    return {'operation': operation, 'label': label, 'reason': issue['fix']}


def overview_payload(frame: pd.DataFrame, profile: dict[str, Any]) -> dict[str, Any]:
    schema = profile.get('schema', {})
    numeric_columns = schema.get('numeric_columns', [])
    date_columns = schema.get('date_columns', [])

    return {
        'cards': overview_cards(frame, profile, numeric_columns),
        'trend': overview_trend(frame, date_columns, numeric_columns),
        'breakdown': overview_breakdown(frame, numeric_columns, date_columns),
        'trend_columns': {
            'date': date_columns[0] if date_columns else None,
            'value': numeric_columns[0] if numeric_columns else None,
        },
    }


def overview_cards(frame: pd.DataFrame, profile: dict[str, Any], numeric_columns: list[str]) -> list[dict[str, Any]]:
    cards = [
        {'label': 'Rows', 'value': profile.get('rows', 0), 'kind': 'count'},
        {'label': 'Columns', 'value': profile.get('columns', 0), 'kind': 'count'},
        {'label': 'Quality score', 'value': profile.get('quality_score', 0), 'suffix': '/100', 'kind': 'quality'},
    ]
    for column in numeric_columns[:3]:
        values = _numeric_series(frame, column).dropna()
        if not values.empty:
            cards.append({'label': column.replace('_', ' ').title(), 'value': round(float(values.sum()), 2), 'kind': 'metric', 'column': column})
    return cards


def overview_trend(frame: pd.DataFrame, date_columns: list[str], numeric_columns: list[str]) -> list[dict[str, Any]]:
    if not date_columns or not numeric_columns:
        return []
    date_column = date_columns[0]
    metric_column = numeric_columns[0]
    periods = pd.to_datetime(frame[date_column], errors='coerce').dt.to_period('M').astype('string')
    values = _numeric_series(frame, metric_column)
    trend_data = pd.DataFrame({'period': periods, 'value': values}).dropna()
    if trend_data.empty:
        return []
    grouped = trend_data.groupby('period', as_index=False)['value'].sum().tail(24)
    return [{'period': str(row['period']), 'value': round(float(row['value']), 2)} for _, row in grouped.iterrows()]


def overview_breakdown(frame: pd.DataFrame, numeric_columns: list[str], date_columns: list[str]) -> list[dict[str, Any]]:
    dimensions = [column for column in frame.columns if column not in numeric_columns and column not in date_columns]
    if not dimensions:
        return []
    counts = frame[dimensions[0]].fillna('(blank)').astype(str).value_counts().head(8)
    return [{'label': str(label), 'value': int(value)} for label, value in counts.items()]


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
