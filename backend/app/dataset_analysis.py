"""Deterministic, in-memory analyses supported by a profiled dataset."""

from __future__ import annotations

from typing import Any

import pandas as pd

from .analytics import _numeric_series


def run_analysis(frame: pd.DataFrame, profile: dict[str, Any], kind: str, column: str | None) -> dict[str, Any]:
    """Run one supported analysis and return its stable API-shaped result."""
    if kind == 'quality':
        return quality_review(profile)

    if not column or column not in frame.columns:
        raise ValueError('This analysis column is not available in the dataset.')

    if kind == 'distribution':
        return distribution(frame, column)

    if kind == 'breakdown':
        return breakdown(frame, column)

    return trend(frame, profile, column, kind)


def quality_review(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        'kind': 'quality',
        'title': 'Data quality review',
        'profile': profile,
        'rows': [],
    }


def distribution(frame: pd.DataFrame, column: str) -> dict[str, Any]:
    values = _numeric_series(frame, column).dropna()
    if values.empty:
        raise ValueError('This field does not contain usable numeric values.')

    bin_count = min(10, max(2, values.nunique()))
    histogram = pd.cut(values, bins=bin_count, duplicates='drop').value_counts().sort_index()
    chart = [{'label': str(label), 'value': int(value)} for label, value in histogram.items()]
    metrics = {
        'count': int(values.size),
        'min': round(float(values.min()), 2),
        'max': round(float(values.max()), 2),
        'mean': round(float(values.mean()), 2),
        'median': round(float(values.median()), 2),
    }
    return {
        'kind': 'distribution',
        'title': f'Distribution of {column}',
        'field': column,
        'aggregation': 'value frequency',
        'metrics': metrics,
        'columns': ['range', 'count'],
        'chart': chart,
    }


def breakdown(frame: pd.DataFrame, column: str) -> dict[str, Any]:
    counts = frame[column].fillna('(blank)').astype(str).value_counts().head(25)
    chart = [{'label': str(label), 'value': int(value)} for label, value in counts.items()]
    return {
        'kind': 'breakdown',
        'title': f'Breakdown by {column}',
        'field': column,
        'aggregation': 'row count',
        'metrics': {'groups': len(chart), 'rows_in_top_groups': sum(point['value'] for point in chart)},
        'columns': [column, 'count'],
        'chart': chart,
    }


def trend(frame: pd.DataFrame, profile: dict[str, Any], column: str, kind: str) -> dict[str, Any]:
    dates = profile.get('schema', {}).get('date_columns', [])
    if not dates:
        raise ValueError('A date field is required for a trend analysis.')

    date_column = dates[0]
    periods = pd.to_datetime(frame[date_column], errors='coerce').dt.to_period('M').astype('string')
    values = _numeric_series(frame, column)
    trend_data = pd.DataFrame({'period': periods, 'value': values}).dropna()
    grouped = trend_data.groupby('period', as_index=False)['value'].sum()

    chart = [{'label': str(row['period']), 'value': round(float(row['value']), 2)} for _, row in grouped.iterrows()]
    metrics = trend_metrics(chart, column) if chart else {}

    return {
        'kind': kind,
        'title': f'Trend of {column}',
        'field': column,
        'aggregation': 'monthly sum',
        'columns': ['period', column],
        'chart': chart,
        'metrics': metrics,
    }


def trend_metrics(chart: list[dict[str, Any]], column: str) -> dict[str, Any]:
    values = [float(point['value']) for point in chart]
    peak = chart[values.index(max(values))]
    low = chart[values.index(min(values))]
    return {
        'metric': column,
        'aggregation': 'monthly sum',
        'periods': len(chart),
        'total': round(sum(values), 2),
        'average': round(sum(values) / len(values), 2),
        'highest_period': {'period': peak['label'], 'value': round(max(values), 2)},
        'lowest_period': {'period': low['label'], 'value': round(min(values), 2)},
    }
