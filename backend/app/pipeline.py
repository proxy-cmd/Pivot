from __future__ import annotations

import pandas as pd


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
            if any(word in str(column).lower() for word in ('date', 'time', 'month', 'year')):
                parsed = pd.to_datetime(frame[column], errors='coerce')
                if parsed.notna().any(): frame[column] = parsed; changed.append(column)
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
