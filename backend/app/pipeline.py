from __future__ import annotations

import pandas as pd

from .analytics import _numeric_series


def apply(frame: pd.DataFrame, operation: str) -> tuple[pd.DataFrame, dict]:
    before = len(frame)
    if operation == 'trim_text':
        columns = frame.select_dtypes(include='object').columns.tolist()
        affected = 0
        for column in columns:
            original = frame[column].copy()
            frame[column] = frame[column].map(lambda value: value.strip() if isinstance(value, str) else value)
            affected += int((original != frame[column]).fillna(False).sum())
        return frame, {'columns': columns, 'affected_rows': affected}
    if operation == 'standardize_format':
        text_columns = frame.select_dtypes(include=['object', 'string']).columns.tolist()
        trimmed_cells = 0
        for column in text_columns:
            original = frame[column].copy()
            frame[column] = frame[column].map(lambda value: value.strip() if isinstance(value, str) else value)
            trimmed_cells += int((original != frame[column]).fillna(False).sum())
        date_columns = []
        invalid_dates = 0
        numeric_columns = []
        numeric_cells = 0
        for column in frame.columns:
            name = str(column).lower()
            if any(word in name for word in ('date', 'time', 'month', 'year')) and not pd.api.types.is_numeric_dtype(frame[column]):
                parsed = pd.to_datetime(frame[column], format='mixed', errors='coerce')
                if parsed.notna().any() or frame[column].notna().any():
                    invalid_dates += int(parsed.isna().sum() - frame[column].isna().sum())
                    frame[column] = parsed.dt.strftime('%Y-%m-%d')
                    date_columns.append(str(column))
                    continue
            numeric = _numeric_series(frame, column)
            non_null = int(frame[column].notna().sum())
            if non_null and numeric.notna().sum() >= max(2, int(non_null * 0.8)) and not any(word in name for word in ('id', 'zip', 'postal', 'phone')):
                original = frame[column].copy()
                frame[column] = numeric
                numeric_cells += int((original.astype('string') != frame[column].astype('string')).fillna(False).sum())
                numeric_columns.append(str(column))
        return frame, {'text_columns': [str(column) for column in text_columns], 'date_columns': date_columns, 'numeric_columns': numeric_columns, 'trimmed_cells': trimmed_cells, 'numeric_cells_normalized': numeric_cells, 'invalid_dates_normalized': max(0, invalid_dates), 'affected_rows': before}
    if operation == 'remove_duplicates':
        frame = frame.drop_duplicates().copy()
        return frame, {'removed_rows': before - len(frame), 'affected_rows': before - len(frame)}
    if operation == 'normalize_columns':
        old = frame.columns.tolist()
        names = []
        seen = {}
        for column in old:
            base = str(column).strip().lower().replace(' ', '_') or 'column'
            seen[base] = seen.get(base, 0) + 1
            names.append(base if seen[base] == 1 else f'{base}_{seen[base]}')
        frame.columns = names
        return frame, {'renamed': dict(zip(old, frame.columns)), 'affected_rows': int(old != names)}
    if operation == 'parse_dates':
        changed = []
        for column in frame.columns:
            if any(word in str(column).lower() for word in ('date', 'time', 'month', 'year')) and not pd.api.types.is_numeric_dtype(frame[column]):
                parsed = pd.to_datetime(frame[column], format='mixed', errors='coerce')
                if parsed.notna().any() or frame[column].notna().any(): frame[column] = parsed.dt.strftime('%Y-%m-%d'); changed.append(column)
        return frame, {'columns': changed, 'affected_rows': before}
    if operation == 'fill_missing':
        changed = 0
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
            changed += missing
        return frame, {'columns': columns, 'filled_values': changed, 'affected_rows': changed}
    if operation == 'remove_outliers':
        numeric = frame.select_dtypes(include='number').columns.tolist()
        if not numeric:
            return frame, {'columns': [], 'removed_rows': 0, 'affected_rows': 0}
        keep = pd.Series(True, index=frame.index)
        for column in numeric:
            q1, q3 = frame[column].quantile([0.25, 0.75])
            iqr = q3 - q1
            if pd.isna(iqr) or iqr == 0:
                continue
            keep &= frame[column].between(q1 - 1.5 * iqr, q3 + 1.5 * iqr) | frame[column].isna()
        cleaned = frame.loc[keep].copy()
        removed = before - len(cleaned)
        return cleaned, {'columns': [str(column) for column in numeric], 'removed_rows': removed, 'affected_rows': removed}
    raise ValueError('Unsupported transformation.')
