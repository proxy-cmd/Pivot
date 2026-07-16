from __future__ import annotations

import re
import hashlib
from dataclasses import dataclass
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
    frame = prepare_frame(frame)
    rows, cols = frame.shape
    missing = int(frame.isna().sum().sum())
    duplicates = int(frame.duplicated().sum())
    total = max(rows * max(cols, 1), 1)
    date_cols = []
    for column in frame.columns:
        parsed = pd.to_datetime(frame[column], format='mixed', errors='coerce')
        non_null = max(int(frame[column].notna().sum()), 1)
        named_date = any(word in column for word in DATE_WORDS)
        value_date = not pd.api.types.is_numeric_dtype(frame[column]) and parsed.notna().sum() >= max(3, int(non_null * 0.8)) and parsed.nunique(dropna=True) >= 3
        if named_date and parsed.notna().sum() >= max(2, int(non_null * 0.2)) or value_date:
            date_cols.append(column)
    ids = [column for column in frame.columns if column.endswith('_id') or any(word in column for word in ID_WORDS)]
    numeric = []
    for column in frame.columns:
        if column in ids or column in date_cols:
            continue
        non_null_numeric = int(_numeric_series(frame, column).notna().sum())
        if pd.api.types.is_numeric_dtype(frame[column]) or (non_null_numeric >= 2 and non_null_numeric >= int(frame[column].notna().sum() * 0.8)):
            numeric.append(column)
    money = [column for column in frame.columns if any(word in column for word in MONEY_WORDS)]
    pii = [column for column in frame.columns if any(word in column for word in ('email', 'phone', 'address', 'ssn', 'dob', 'first_name', 'last_name'))]
    categoricals = [column for column in frame.columns if column not in numeric and column not in date_cols]
    whitespace = sum(int(frame[column].astype(str).str.contains(r'^\s+|\s+$', regex=True, na=False).sum()) for column in categoricals)
    semantic = []
    column_stats = []
    for column in frame.columns:
        kind = 'dimension'; confidence = 0.62
        name = column.lower()
        if column in ids: kind, confidence = 'identifier', 0.93
        elif column in money: kind, confidence = 'monetary_metric', 0.88
        elif column in date_cols: kind, confidence = 'time_dimension', 0.86
        elif any(word in name for word in ('region', 'country', 'city', 'state', 'zip')): kind, confidence = 'geographic_dimension', 0.81
        elif column in numeric: kind, confidence = 'numeric_metric', 0.76
        values = frame[column]
        numeric_values = _numeric_series(frame, column) if column in numeric else pd.Series(dtype=float)
        non_null = values.dropna()
        examples = [str(value) for value in non_null.head(3).tolist()]
        stats: dict[str, Any] = {
            'column': column,
            'dtype': str(values.dtype),
            'role': kind,
            'confidence': confidence,
            'null_count': int(values.isna().sum()),
            'null_pct': round(float(values.isna().mean() * 100), 2),
            'unique_count': int(values.nunique(dropna=True)),
            'unique_pct': round(float(values.nunique(dropna=True) / max(rows, 1) * 100), 2),
            'examples': examples,
        }
        if column in numeric:
            clean_numeric = numeric_values.dropna()
            stats.update({
                'min': float(clean_numeric.min()) if len(clean_numeric) else None,
                'max': float(clean_numeric.max()) if len(clean_numeric) else None,
                'mean': round(float(clean_numeric.mean()), 4) if len(clean_numeric) else None,
                'median': round(float(clean_numeric.median()), 4) if len(clean_numeric) else None,
            })
        semantic.append({'column': column, 'role': kind, 'confidence': confidence, 'evidence': f'Name and values match {kind.replace("_", " ")} patterns.'})
        column_stats.append(stats)
    invalid_dates = 0
    for column in date_cols:
        parsed = pd.to_datetime(frame[column], format='mixed', errors='coerce')
        invalid_dates += int(parsed.isna().sum() - frame[column].isna().sum())
    negatives = 0
    for column in numeric:
        numeric_values = _numeric_series(frame, column)
        if any(word in column for word in ('quantity', 'units', 'stock', 'price', 'amount', 'cost')):
            negatives += int((numeric_values < 0).sum())
    outliers = 0
    if rows >= 12 and numeric:
        source = frame.sample(min(rows, 10000), random_state=42) if rows > 10000 else frame
        sample = pd.DataFrame({column: _numeric_series(source, column) for column in numeric}).replace([np.inf, -np.inf], np.nan).dropna()
        if len(sample) >= 12:
            outliers = int((IsolationForest(contamination=0.05, random_state=42).fit_predict(sample) == -1).sum())
    issues = []
    if missing:
        issues.append({'type': 'missing_values', 'count': missing, 'impact': 'Incomplete fields can distort segmentation and reporting.', 'fix': 'Fill safe defaults or flag records for review.'})
    if duplicates:
        issues.append({'type': 'duplicate_records', 'count': duplicates, 'impact': 'Duplicate records can overstate revenue and customer counts.', 'fix': 'Remove exact duplicate rows after review.'})
    if invalid_dates:
        issues.append({'type': 'invalid_dates', 'count': invalid_dates, 'impact': 'Invalid dates break period-over-period analysis.', 'fix': 'Normalize date formats before aggregation.'})
    if negatives:
        issues.append({'type': 'negative_values', 'count': negatives, 'impact': 'Negative operational values may represent returns or entry errors.', 'fix': 'Classify returns separately and validate remaining values.'})
    if outliers:
        issues.append({'type': 'outliers', 'count': outliers, 'impact': 'Extreme records can skew averages and forecasts.', 'fix': 'Review flagged values before excluding them.'})
    if whitespace:
        issues.append({'type': 'whitespace', 'count': whitespace, 'impact': 'Leading or trailing whitespace creates duplicate categories.', 'fix': 'Review and approve text trimming.'})
    penalty = min(55, (missing / total) * 100 + (duplicates / max(rows, 1)) * 30 + invalid_dates * 1.5 + negatives * 0.5 + outliers * 0.4)
    keys = [column for column in ids if frame[column].nunique(dropna=True) == rows]
    consistency = max(0, 100 - round((invalid_dates / max(rows * max(len(date_cols), 1), 1)) * 100))
    completeness = round(100 - (missing / total) * 100, 2)
    uniqueness = round(100 - (duplicates / max(rows, 1)) * 100, 2)
    return {
        'file_name': filename, 'role': role_for(frame.columns.tolist()), 'rows': rows, 'columns': cols,
        'fingerprint': hashlib.sha256(frame.to_csv(index=False).encode()).hexdigest(),
        'quality_score': max(45, round(100 - penalty)), 'issues': issues, 'schema': {
            'date_columns': date_cols, 'numeric_columns': numeric, 'currency_columns': money,
            'candidate_primary_keys': keys, 'candidate_ids': ids,
            'pii_columns': pii, 'semantic_columns': semantic, 'column_stats': column_stats,
        },
        'metrics': {'completeness': completeness, 'consistency': consistency, 'uniqueness': uniqueness, 'missing_cells': missing, 'duplicate_rows': duplicates},
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
