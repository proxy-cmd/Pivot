from __future__ import annotations

import re
import hashlib
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.linear_model import LinearRegression


DATE_WORDS = ('date', 'time', 'month', 'year', 'created', 'ordered')
MONEY_WORDS = ('revenue', 'sales', 'amount', 'price', 'cost', 'profit', 'total', 'margin')
ID_WORDS = ('id', 'key', 'code', 'sku', 'email')


def clean_name(name: str) -> str:
    return re.sub(r'[^a-z0-9]+', '_', str(name).lower()).strip('_')


def normalize_columns(columns: list[str]) -> list[str]:
    """Return stable SQL-safe names without mutating the source file."""
    result = []
    seen: dict[str, int] = {}
    for raw in columns:
        base = clean_name(raw) or 'column'
        seen[base] = seen.get(base, 0) + 1
        result.append(base if seen[base] == 1 else f'{base}_{seen[base]}')
    return result


def prepare_frame(frame: pd.DataFrame) -> pd.DataFrame:
    prepared = frame.copy()
    prepared.columns = normalize_columns([str(column) for column in prepared.columns])
    return prepared


def _numeric_series(frame: pd.DataFrame, column: str) -> pd.Series:
    values = frame[column]
    if pd.api.types.is_numeric_dtype(values):
        return pd.to_numeric(values, errors='coerce')
    cleaned = values.astype('string').str.replace(r'[^0-9.\-]', '', regex=True)
    return pd.to_numeric(cleaned, errors='coerce')


def role_for(columns: list[str]) -> str:
    text = ' '.join(columns).lower()
    if any(word in text for word in ('order', 'revenue', 'sale', 'transaction')):
        return 'Sales & orders'
    if any(word in text for word in ('inventory', 'stock', 'warehouse', 'sku')):
        return 'Inventory'
    if any(word in text for word in ('customer', 'email', 'segment', 'account')):
        return 'Customers'
    if any(word in text for word in ('expense', 'vendor', 'invoice', 'payment')):
        return 'Finance & expenses'
    return 'Operational data'


def profile_frame(frame: pd.DataFrame, filename: str) -> dict[str, Any]:
    prepared_frame = prepare_frame(frame)
    schema = infer_schema(prepared_frame)
    quality = assess_quality(prepared_frame, schema)

    return profile_response(prepared_frame, filename, schema, quality)


def infer_schema(frame: pd.DataFrame) -> dict[str, Any]:
    date_columns = find_date_columns(frame)
    identifier_columns = find_identifier_columns(frame)
    numeric_columns = find_numeric_columns(frame, identifier_columns, date_columns)
    currency_columns = matching_columns(frame.columns, MONEY_WORDS)
    pii_columns = matching_columns(frame.columns, ('email', 'phone', 'address', 'ssn', 'dob', 'first_name', 'last_name'))
    primary_keys = [column for column in identifier_columns if frame[column].nunique(dropna=True) == len(frame)]
    column_stats, semantic_columns = describe_columns(frame, identifier_columns, date_columns, numeric_columns, currency_columns)

    return {
        'date_columns': date_columns,
        'numeric_columns': numeric_columns,
        'currency_columns': currency_columns,
        'candidate_primary_keys': primary_keys,
        'candidate_ids': identifier_columns,
        'pii_columns': pii_columns,
        'semantic_columns': semantic_columns,
        'column_stats': column_stats,
    }


def find_date_columns(frame: pd.DataFrame) -> list[str]:
    date_columns = []
    for column in frame.columns:
        if column_is_date(frame[column], column):
            date_columns.append(column)
    return date_columns


def column_is_date(values: pd.Series, column: str) -> bool:
    sample_values = values.dropna().head(1000)
    parsed_dates = pd.to_datetime(sample_values, format='mixed', errors='coerce')
    non_null_count = max(int(values.notna().sum()), 1)
    has_date_name = any(word in column for word in DATE_WORDS)
    has_date_values = (
        not pd.api.types.is_numeric_dtype(values)
        and parsed_dates.notna().sum() >= max(3, int(len(sample_values) * 0.8))
        and parsed_dates.nunique(dropna=True) >= 3
    )
    named_dates_are_parseable = has_date_name and parsed_dates.notna().sum() >= max(1, int(non_null_count * 0.2))
    return named_dates_are_parseable or has_date_values


def find_identifier_columns(frame: pd.DataFrame) -> list[str]:
    return [column for column in frame.columns if column.endswith('_id') or any(word in column for word in ID_WORDS)]


def find_numeric_columns(frame: pd.DataFrame, identifiers: list[str], date_columns: list[str]) -> list[str]:
    numeric_columns = []
    for column in frame.columns:
        if column in identifiers or column in date_columns:
            continue
        if column_is_numeric(frame, column):
            numeric_columns.append(column)
    return numeric_columns


def column_is_numeric(frame: pd.DataFrame, column: str) -> bool:
    values = frame[column]
    numeric_values = _numeric_series(frame, column)
    numeric_count = int(numeric_values.notna().sum())
    required_count = int(values.notna().sum() * 0.8)
    return pd.api.types.is_numeric_dtype(values) or (numeric_count >= 2 and numeric_count >= required_count)


def matching_columns(columns: pd.Index, words: tuple[str, ...]) -> list[str]:
    return [column for column in columns if any(word in column for word in words)]


def describe_columns(
    frame: pd.DataFrame,
    identifiers: list[str],
    date_columns: list[str],
    numeric_columns: list[str],
    currency_columns: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    stats = []
    semantic_columns = []
    for column in frame.columns:
        role, confidence = column_role(column, identifiers, date_columns, numeric_columns, currency_columns)
        stats.append(column_stats(frame, column, role, confidence, numeric_columns))
        semantic_columns.append({
            'column': column,
            'role': role,
            'confidence': confidence,
            'evidence': f'Name and values match {role.replace("_", " ")} patterns.',
        })
    return stats, semantic_columns


def column_role(column: str, identifiers: list[str], date_columns: list[str], numeric_columns: list[str], currency_columns: list[str]) -> tuple[str, float]:
    if column in identifiers:
        return 'identifier', 0.93
    if column in currency_columns:
        return 'monetary_metric', 0.88
    if column in date_columns:
        return 'time_dimension', 0.86
    if any(word in column for word in ('region', 'country', 'city', 'state', 'zip')):
        return 'geographic_dimension', 0.81
    if column in numeric_columns:
        return 'numeric_metric', 0.76
    return 'dimension', 0.62


def column_stats(frame: pd.DataFrame, column: str, role: str, confidence: float, numeric_columns: list[str]) -> dict[str, Any]:
    values = frame[column]
    non_null = values.dropna()
    stats = {
        'column': column,
        'dtype': str(values.dtype),
        'role': role,
        'confidence': confidence,
        'null_count': int(values.isna().sum()),
        'null_pct': round(float(values.isna().mean() * 100), 2),
        'unique_count': int(values.nunique(dropna=True)),
        'unique_pct': round(float(values.nunique(dropna=True) / max(len(frame), 1) * 100), 2),
        'examples': [str(value) for value in non_null.head(3).tolist()],
    }
    if column in numeric_columns:
        stats.update(numeric_stats(_numeric_series(frame, column)))
    return stats


def numeric_stats(values: pd.Series) -> dict[str, float | None]:
    usable_values = values.dropna()
    if usable_values.empty:
        return {'min': None, 'max': None, 'mean': None, 'median': None}
    return {
        'min': float(usable_values.min()),
        'max': float(usable_values.max()),
        'mean': round(float(usable_values.mean()), 4),
        'median': round(float(usable_values.median()), 4),
    }


def assess_quality(frame: pd.DataFrame, schema: dict[str, Any]) -> dict[str, Any]:
    missing_cells = int(frame.isna().sum().sum())
    duplicate_rows = int(frame.duplicated().sum())
    invalid_dates = invalid_date_count(frame, schema['date_columns'])
    negative_values = negative_value_count(frame, schema['numeric_columns'])
    outliers = outlier_count(frame, schema['numeric_columns'])
    whitespace = whitespace_count(frame, schema['numeric_columns'], schema['date_columns'])
    issues = quality_issues(missing_cells, duplicate_rows, invalid_dates, negative_values, outliers, whitespace)

    return {
        'missing_cells': missing_cells,
        'duplicate_rows': duplicate_rows,
        'invalid_dates': invalid_dates,
        'negative_values': negative_values,
        'outliers': outliers,
        'whitespace': whitespace,
        'issues': issues,
    }


def invalid_date_count(frame: pd.DataFrame, date_columns: list[str]) -> int:
    invalid_dates = 0
    for column in date_columns:
        parsed_dates = pd.to_datetime(frame[column], format='mixed', errors='coerce')
        invalid_dates += int(parsed_dates.isna().sum() - frame[column].isna().sum())
    return invalid_dates


def negative_value_count(frame: pd.DataFrame, numeric_columns: list[str]) -> int:
    relevant_words = ('quantity', 'units', 'stock', 'price', 'amount', 'cost')
    negatives = 0
    for column in numeric_columns:
        if any(word in column for word in relevant_words):
            negatives += int((_numeric_series(frame, column) < 0).sum())
    return negatives


def outlier_count(frame: pd.DataFrame, numeric_columns: list[str]) -> int:
    if len(frame) < 12 or not numeric_columns:
        return 0
    source = frame.sample(min(len(frame), 10000), random_state=42) if len(frame) > 10000 else frame
    numeric_sample = pd.DataFrame({column: _numeric_series(source, column) for column in numeric_columns})
    usable_sample = numeric_sample.replace([np.inf, -np.inf], np.nan).dropna()
    if len(usable_sample) < 12:
        return 0
    predictions = IsolationForest(contamination=0.05, random_state=42).fit_predict(usable_sample)
    return int((predictions == -1).sum())


def whitespace_count(frame: pd.DataFrame, numeric_columns: list[str], date_columns: list[str]) -> int:
    categorical_columns = [column for column in frame.columns if column not in numeric_columns and column not in date_columns]
    return sum(
        int(frame[column].astype(str).str.contains(r'^\s+|\s+$', regex=True, na=False).sum())
        for column in categorical_columns
    )


def quality_issues(missing: int, duplicates: int, invalid_dates: int, negatives: int, outliers: int, whitespace: int) -> list[dict[str, Any]]:
    issue_definitions = [
        ('missing_values', missing, 'Incomplete fields can distort segmentation and reporting.', 'Fill safe defaults or flag records for review.'),
        ('duplicate_records', duplicates, 'Duplicate records can overstate revenue and customer counts.', 'Remove exact duplicate rows after review.'),
        ('invalid_dates', invalid_dates, 'Invalid dates break period-over-period analysis.', 'Normalize date formats before aggregation.'),
        ('negative_values', negatives, 'Negative operational values may represent returns or entry errors.', 'Classify returns separately and validate remaining values.'),
        ('outliers', outliers, 'Extreme records can skew averages and forecasts.', 'Review flagged values before excluding them.'),
        ('whitespace', whitespace, 'Leading or trailing whitespace creates duplicate categories.', 'Review and approve text trimming.'),
    ]
    return [
        {'type': kind, 'count': count, 'impact': impact, 'fix': fix}
        for kind, count, impact, fix in issue_definitions
        if count
    ]


def profile_response(frame: pd.DataFrame, filename: str, schema: dict[str, Any], quality: dict[str, Any]) -> dict[str, Any]:
    rows, columns = frame.shape
    total_cells = max(rows * max(columns, 1), 1)
    penalty = quality_penalty(quality, rows, total_cells)

    return {
        'file_name': filename,
        'role': role_for(frame.columns.tolist()),
        'rows': rows,
        'columns': columns,
        'fingerprint': hashlib.sha256(frame.to_csv(index=False).encode()).hexdigest(),
        'quality_score': max(45, round(100 - penalty)),
        'issues': quality['issues'],
        'schema': schema,
        'metrics': quality_metrics(quality, rows, total_cells, len(schema['date_columns'])),
    }


def quality_penalty(quality: dict[str, Any], rows: int, total_cells: int) -> float:
    missing_penalty = quality['missing_cells'] / total_cells * 100
    duplicate_penalty = quality['duplicate_rows'] / max(rows, 1) * 30
    return min(55, missing_penalty + duplicate_penalty + quality['invalid_dates'] * 1.5 + quality['negative_values'] * 0.5 + quality['outliers'] * 0.4)


def quality_metrics(quality: dict[str, Any], rows: int, total_cells: int, date_column_count: int) -> dict[str, Any]:
    missing = quality['missing_cells']
    duplicates = quality['duplicate_rows']
    invalid_dates = quality['invalid_dates']
    date_cells = max(rows * max(date_column_count, 1), 1)
    return {
        'completeness': round(100 - missing / total_cells * 100, 2),
        'consistency': max(0, 100 - round(invalid_dates / date_cells * 100)),
        'uniqueness': round(100 - duplicates / max(rows, 1) * 100, 2),
        'missing_cells': missing,
        'duplicate_rows': duplicates,
    }


def forecast(values: list[float]) -> dict[str, Any]:
    series = np.asarray(values, dtype=float)
    if len(series) < 3:
        return {'available': False, 'reason': 'At least three time periods are needed for a reliable forecast.'}
    x = np.arange(len(series)).reshape(-1, 1)
    model = LinearRegression().fit(x, series)
    future_x = np.arange(len(series), len(series) + 3).reshape(-1, 1)
    predicted = model.predict(future_x)
    residual = series - model.predict(x)
    spread = max(float(np.std(residual) * 1.96), float(np.mean(series) * 0.04))
    return {
        'available': True, 'forecast': [round(float(value), 2) for value in predicted],
        'lower': [round(float(value - spread), 2) for value in predicted],
        'upper': [round(float(value + spread), 2) for value in predicted],
        'confidence': 'medium' if len(series) < 12 else 'high',
        'assumption': 'Linear trend projection. Seasonality requires at least 12 clean monthly periods.',
    }


def scenario(price: float, marketing: float, costs: float, baseline: float) -> dict[str, Any]:
    revenue = baseline * (1 + (price * 0.55 + marketing * 0.28) / 100)
    cost_pressure = round(max(0, costs * 0.46), 1)
    return {'revenue': round(revenue), 'change': round((revenue / baseline - 1) * 100, 1), 'cost_pressure': cost_pressure, 'assumption': 'Revenue change uses the supplied baseline and scenario percentages; no dataset margin is assumed.'}
