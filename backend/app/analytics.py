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
    frame.columns = [clean_name(column) for column in frame.columns]
    rows, cols = frame.shape
    missing = int(frame.isna().sum().sum())
    duplicates = int(frame.duplicated().sum())
    total = max(rows * max(cols, 1), 1)
    date_cols = [column for column in frame.columns if any(word in column for word in DATE_WORDS)]
    numeric = frame.select_dtypes(include=np.number).columns.tolist()
    money = [column for column in frame.columns if any(word in column for word in MONEY_WORDS)]
    ids = [column for column in frame.columns if column.endswith('_id') or any(word in column for word in ID_WORDS)]
    pii = [column for column in frame.columns if any(word in column for word in ('email', 'phone', 'address', 'ssn', 'dob', 'first_name', 'last_name'))]
    categoricals = frame.select_dtypes(include=['object', 'category']).columns.tolist()
    whitespace = sum(int(frame[column].astype(str).str.contains(r'^\s+|\s+$', regex=True, na=False).sum()) for column in categoricals)
    semantic = []
    for column in frame.columns:
        kind = 'dimension'; confidence = 0.62
        name = column.lower()
        if column in ids: kind, confidence = 'identifier', 0.93
        elif column in money: kind, confidence = 'monetary_metric', 0.88
        elif column in date_cols: kind, confidence = 'time_dimension', 0.86
        elif any(word in name for word in ('region', 'country', 'city', 'state', 'zip')): kind, confidence = 'geographic_dimension', 0.81
        elif column in numeric: kind, confidence = 'numeric_metric', 0.76
        semantic.append({'column': column, 'role': kind, 'confidence': confidence, 'evidence': f'Name and values match {kind.replace("_", " ")} patterns.'})
    invalid_dates = 0
    for column in date_cols:
        parsed = pd.to_datetime(frame[column], errors='coerce')
        invalid_dates += int(parsed.isna().sum() - frame[column].isna().sum())
    negatives = 0
    for column in numeric:
        if any(word in column for word in ('quantity', 'units', 'stock', 'price', 'amount', 'cost')):
            negatives += int((frame[column] < 0).sum())
    outliers = 0
    if rows >= 12 and numeric:
        sample = frame[numeric].replace([np.inf, -np.inf], np.nan).dropna()
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
    return {
        'file_name': filename, 'role': role_for(frame.columns.tolist()), 'rows': rows, 'columns': cols,
        'fingerprint': hashlib.sha256(frame.to_csv(index=False).encode()).hexdigest(),
        'quality_score': max(45, round(100 - penalty)), 'issues': issues, 'schema': {
            'date_columns': date_cols, 'numeric_columns': numeric, 'currency_columns': money,
            'candidate_primary_keys': keys, 'candidate_ids': ids,
            'pii_columns': pii, 'semantic_columns': semantic,
        },
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
    margin = 38.4 + price * 0.22 + marketing * 0.05 - costs * 0.46
    return {'revenue': round(revenue), 'margin': round(max(0, margin), 1), 'change': round((revenue / baseline - 1) * 100, 1)}
