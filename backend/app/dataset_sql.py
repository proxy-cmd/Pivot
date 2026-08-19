"""Read-only SQLite execution against an in-memory dataset dataframe."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

import pandas as pd

from .gemini import generate as generate_gemini

QUALITY_QUESTION_WORDS = ('quality', 'missing', 'duplicate', 'clean')
TREND_QUESTION_WORDS = ('trend', 'month', 'time')
TOP_QUESTION_WORDS = ('top', 'most', 'highest', 'best')
SUMMARY_QUESTION_WORDS = ('average', 'mean', 'sum', 'total', 'how much', 'revenue', 'sales')
METRIC_NAME_WORDS = ('revenue', 'sales', 'amount', 'price', 'cost', 'total', 'profit')
DIMENSION_NAME_WORDS = ('customer', 'product', 'region', 'country', 'category', 'department', 'name')


def quote_identifier(value: str) -> str:
    return '"' + str(value).replace('"', '""') + '"'


def execute_query(frame: pd.DataFrame, query: str) -> dict[str, Any]:
    sql_frame = frame.copy()

    normalize_date_columns(sql_frame)

    with sqlite3.connect(':memory:') as database:
        sql_frame.to_sql('dataset', database, index=False, if_exists='replace')
        query_result = pd.read_sql_query(query, database)

    return query_response(query_result)


def normalize_date_columns(frame: pd.DataFrame) -> None:
    for column in frame.select_dtypes(include=['object', 'string']).columns:
        if not looks_like_date_column(column):
            continue

        parsed_dates = pd.to_datetime(frame[column], format='mixed', errors='coerce')
        if parsed_dates.notna().mean() < 0.2:
            continue

        frame[column] = parsed_dates.dt.strftime('%Y-%m-%d')


def looks_like_date_column(column: Any) -> bool:
    column_name = str(column).lower()
    return any(word in column_name for word in ('date', 'time', 'month', 'year'))


def query_response(result: pd.DataFrame) -> dict[str, Any]:
    rows = result.head(200).fillna('').to_json(orient='records')
    return {
        'columns': result.columns.tolist(),
        'rows': json.loads(rows),
        'count': len(result),
    }


def deterministic_query(question: str, item: dict[str, Any]) -> str | None:
    schema = dataset_schema(item)
    question_text = question.lower()
    metric = preferred_column(schema['numeric'], METRIC_NAME_WORDS)
    dimension = preferred_column(schema['dimensions'], DIMENSION_NAME_WORDS)

    if contains_any(question_text, QUALITY_QUESTION_WORDS):
        return 'SELECT * FROM dataset LIMIT 1'
    if contains_any(question_text, TREND_QUESTION_WORDS) and schema['dates'] and metric:
        return trend_query(schema['dates'][0], metric)
    if contains_any(question_text, TOP_QUESTION_WORDS) and metric and dimension:
        return ranking_query(dimension, metric, question_text)
    if metric and contains_any(question_text, SUMMARY_QUESTION_WORDS):
        aggregate = 'AVG' if contains_any(question_text, ('average', 'mean')) else 'SUM'
        return f'SELECT {aggregate}({quote_identifier(metric)}) AS value FROM dataset'
    return None


def dataset_schema(dataset: dict[str, Any]) -> dict[str, list[str]]:
    profile = dataset.get('profile') or {}
    schema = profile.get('schema') or {}
    numeric = schema.get('numeric_columns') or []
    dates = schema.get('date_columns') or []
    columns = profile.get('columns_list') or []
    dimensions = [column for column in columns if column not in numeric and column not in dates]
    return {'numeric': numeric, 'dates': dates, 'dimensions': dimensions}


def preferred_column(columns: list[str], keywords: tuple[str, ...]) -> str | None:
    for column in columns:
        if contains_any(column.lower(), keywords):
            return column
    return columns[0] if columns else None


def contains_any(text: str, words: tuple[str, ...]) -> bool:
    return any(word in text for word in words)


def trend_query(date_column: str, metric: str) -> str:
    return (
        f"SELECT strftime('%Y-%m', {quote_identifier(date_column)}) AS period, "
        f"SUM({quote_identifier(metric)}) AS value FROM dataset "
        'GROUP BY period ORDER BY period'
    )


def ranking_query(dimension: str, metric: str, question: str) -> str:
    limit = 50 if '50' in question else 20
    return (
        f'SELECT {quote_identifier(dimension)} AS dimension, '
        f'SUM({quote_identifier(metric)}) AS value FROM dataset '
        f'GROUP BY {quote_identifier(dimension)} ORDER BY value DESC LIMIT {limit}'
    )


def generate_query(question: str, item: dict[str, Any]) -> str | None:
    columns = (item.get('profile') or {}).get('columns_list', [])
    prompt = (
        'Return only one SQLite SELECT query. The table is dataset. '
        f'Allowed columns are {columns}. Never use markdown, semicolons, or write operations. '
        f'Question: {question}'
    )
    response = generate_gemini(prompt)
    if not response:
        return None
    return response.replace('```sql', '').replace('```', '').strip()
