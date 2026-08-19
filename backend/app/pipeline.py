"""Pure, version-safe dataframe transformations."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

import pandas as pd

from .analytics import _numeric_series

Transformation = Callable[[pd.DataFrame], tuple[pd.DataFrame, dict[str, Any]]]
DATE_NAME_PARTS = ('date', 'time', 'month', 'year')
IDENTIFIER_NAME_PARTS = ('id', 'zip', 'postal', 'phone')


def apply(frame: pd.DataFrame, operation: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Apply one supported transformation without mutating ``frame``."""
    handler = OPERATIONS.get(operation)
    if not handler:
        raise ValueError('Unsupported transformation.')
    return handler(frame.copy())


def trim_text(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    columns = text_columns(frame)
    affected_cells = 0
    for column in columns:
        original = frame[column].copy()
        frame[column] = frame[column].map(strip_text)
        affected_cells += changed_cells(original, frame[column])
    return frame, {'columns': [str(column) for column in columns], 'affected_rows': affected_cells}


def standardize_format(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    frame, text_metrics = trim_text(frame)
    date_columns, invalid_dates = normalize_dates(frame)
    numeric_columns, numeric_cells = normalize_numbers(frame)
    return frame, {
        'text_columns': text_metrics['columns'],
        'date_columns': date_columns,
        'numeric_columns': numeric_columns,
        'trimmed_cells': text_metrics['affected_rows'],
        'numeric_cells_normalized': numeric_cells,
        'invalid_dates_normalized': invalid_dates,
        'affected_rows': len(frame),
    }


def remove_duplicates(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    cleaned = frame.drop_duplicates().copy()
    removed_rows = len(frame) - len(cleaned)
    return cleaned, {'removed_rows': removed_rows, 'affected_rows': removed_rows}


def normalize_columns(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    original = frame.columns.tolist()
    normalized = unique_column_names(original)
    frame.columns = normalized
    return frame, {'renamed': dict(zip(original, normalized)), 'affected_rows': int(original != normalized)}


def parse_dates(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    columns, _ = normalize_dates(frame)
    return frame, {'columns': columns, 'affected_rows': len(frame)}


def fill_missing(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    changed_values = 0
    columns = []
    for column in frame.columns:
        missing = int(frame[column].isna().sum())
        if not missing:
            continue
        columns.append(str(column))
        if pd.api.types.is_numeric_dtype(frame[column]):
            frame[column] = frame[column].fillna(frame[column].median())
        else:
            mode = frame[column].mode(dropna=True)
            frame[column] = frame[column].fillna(mode.iloc[0] if not mode.empty else '(blank)')
        changed_values += missing
    return frame, {'columns': columns, 'filled_values': changed_values, 'affected_rows': changed_values}


def remove_outliers(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    numeric_columns = frame.select_dtypes(include='number').columns.tolist()
    if not numeric_columns:
        return frame, {'columns': [], 'removed_rows': 0, 'affected_rows': 0}
    keep = pd.Series(True, index=frame.index)
    for column in numeric_columns:
        lower, upper = outlier_bounds(frame[column])
        if lower is not None and upper is not None:
            keep &= frame[column].between(lower, upper) | frame[column].isna()
    cleaned = frame.loc[keep].copy()
    removed_rows = len(frame) - len(cleaned)
    return cleaned, {'columns': [str(column) for column in numeric_columns], 'removed_rows': removed_rows, 'affected_rows': removed_rows}


def text_columns(frame: pd.DataFrame) -> list[Any]:
    return frame.select_dtypes(include=['object', 'string']).columns.tolist()


def strip_text(value: Any) -> Any:
    return value.strip() if isinstance(value, str) else value


def changed_cells(before: pd.Series, after: pd.Series) -> int:
    return int((before != after).fillna(False).sum())


def normalize_dates(frame: pd.DataFrame) -> tuple[list[str], int]:
    columns = []
    invalid_dates = 0
    for column in frame.columns:
        if not is_date_column(frame[column], str(column)):
            continue
        parsed = pd.to_datetime(frame[column], format='mixed', errors='coerce')
        invalid_dates += int(parsed.isna().sum() - frame[column].isna().sum())
        frame[column] = parsed.dt.strftime('%Y-%m-%d')
        columns.append(str(column))
    return columns, max(0, invalid_dates)


def is_date_column(values: pd.Series, name: str) -> bool:
    if pd.api.types.is_numeric_dtype(values):
        return False
    if any(part in name.lower() for part in DATE_NAME_PARTS):
        return True
    sample = values.dropna().head(100)
    if sample.empty:
        return False
    parsed = pd.to_datetime(sample, format='mixed', errors='coerce')
    return parsed.notna().mean() >= 0.6 and parsed.nunique(dropna=True) >= 3


def normalize_numbers(frame: pd.DataFrame) -> tuple[list[str], int]:
    columns = []
    changed_values = 0
    for column in frame.columns:
        if any(part in str(column).lower() for part in IDENTIFIER_NAME_PARTS):
            continue
        numeric = _numeric_series(frame, column)
        non_null = int(frame[column].notna().sum())
        if not non_null or numeric.notna().sum() < max(2, int(non_null * 0.8)):
            continue
        original = frame[column].copy()
        frame[column] = numeric
        changed_values += changed_cells(original.astype('string'), frame[column].astype('string'))
        columns.append(str(column))
    return columns, changed_values


def unique_column_names(columns: list[Any]) -> list[str]:
    names: list[str] = []
    counts: dict[str, int] = {}
    for column in columns:
        base = re.sub(r'[^a-z0-9]+', '_', str(column).strip().lower()).strip('_') or 'column'
        counts[base] = counts.get(base, 0) + 1
        names.append(base if counts[base] == 1 else f'{base}_{counts[base]}')
    return names


def outlier_bounds(values: pd.Series) -> tuple[float | None, float | None]:
    lower_quartile, upper_quartile = values.quantile([0.25, 0.75])
    spread = upper_quartile - lower_quartile
    if pd.isna(spread) or spread == 0:
        return None, None
    return lower_quartile - 1.5 * spread, upper_quartile + 1.5 * spread


OPERATIONS: dict[str, Transformation] = {
    'trim_text': trim_text,
    'standardize_format': standardize_format,
    'remove_duplicates': remove_duplicates,
    'normalize_columns': normalize_columns,
    'parse_dates': parse_dates,
    'fill_missing': fill_missing,
    'remove_outliers': remove_outliers,
}
