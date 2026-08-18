"""Read-only SQLite execution against an in-memory dataset dataframe."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

import pandas as pd


def quote_identifier(value: str) -> str:
    return '"' + str(value).replace('"', '""') + '"'


def execute_query(frame: pd.DataFrame, query: str) -> dict[str, Any]:
    database = sqlite3.connect(':memory:')
    try:
        sql_frame = frame.copy()
        for column in sql_frame.select_dtypes(include=['object', 'string']).columns:
            if any(word in str(column).lower() for word in ('date', 'time', 'month', 'year')):
                parsed = pd.to_datetime(sql_frame[column], format='mixed', errors='coerce')
                if parsed.notna().mean() >= 0.2:
                    sql_frame[column] = parsed.dt.strftime('%Y-%m-%d')
        sql_frame.to_sql('dataset', database, index=False, if_exists='replace')
        result = pd.read_sql_query(query, database)
        return {'columns': result.columns.tolist(), 'rows': json.loads(result.head(200).fillna('').to_json(orient='records')), 'count': int(len(result))}
    finally:
        database.close()


def deterministic_query(question: str, item: dict[str, Any]) -> str | None:
    profile = item.get('profile') or {}
    columns = profile.get('columns_list', [])
    numeric = profile.get('schema', {}).get('numeric_columns', [])
    dates = profile.get('schema', {}).get('date_columns', [])
    dimensions = [column for column in columns if column not in numeric and column not in dates]
    text = question.lower()
    metric = next((column for column in numeric if any(word in column.lower() for word in ('revenue', 'sales', 'amount', 'price', 'cost', 'total', 'profit'))), numeric[0] if numeric else None)
    dimension = next((column for column in dimensions if any(word in column.lower() for word in ('customer', 'product', 'region', 'country', 'category', 'department', 'name'))), dimensions[0] if dimensions else None)
    if any(word in text for word in ('quality', 'missing', 'duplicate', 'clean')):
        return 'SELECT * FROM dataset LIMIT 1'
    if ('trend' in text or 'month' in text or 'time' in text) and dates and metric:
        return f"SELECT strftime('%Y-%m', {quote_identifier(dates[0])}) AS period, SUM({quote_identifier(metric)}) AS value FROM dataset GROUP BY period ORDER BY period"
    if any(word in text for word in ('top', 'most', 'highest', 'best')) and metric and dimension:
        limit = 50 if '50' in text else 20
        return f'SELECT {quote_identifier(dimension)} AS dimension, SUM({quote_identifier(metric)}) AS value FROM dataset GROUP BY {quote_identifier(dimension)} ORDER BY value DESC LIMIT {limit}'
    if metric and any(word in text for word in ('average', 'mean', 'sum', 'total', 'how much', 'revenue', 'sales')):
        aggregate = 'AVG' if any(word in text for word in ('average', 'mean')) else 'SUM'
        return f'SELECT {aggregate}({quote_identifier(metric)}) AS value FROM dataset'
    return None


def generate_query(question: str, item: dict[str, Any], api_key: str, model: str) -> str | None:
    if not api_key:
        return None
    columns = (item.get('profile') or {}).get('columns_list', [])
    prompt = f'''Return only one SQLite SELECT query for the question. The table is dataset. Allowed columns are {columns}. Never use markdown, semicolons, or write operations. Question: {question}'''
    try:
        from google import genai
        text = genai.Client(api_key=api_key).models.generate_content(model=model, contents=prompt).text or ''
        return text.replace('```sql', '').replace('```', '').strip()
    except Exception:
        return None
