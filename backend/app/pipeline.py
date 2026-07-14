from __future__ import annotations

import pandas as pd


def apply(frame: pd.DataFrame, operation: str) -> tuple[pd.DataFrame, dict]:
    before = len(frame)
    if operation == 'trim_text':
        columns = frame.select_dtypes(include='object').columns.tolist()
        for column in columns:
            frame[column] = frame[column].map(lambda value: value.strip() if isinstance(value, str) else value)
        return frame, {'columns': columns, 'affected_rows': before}
    if operation == 'remove_duplicates':
        frame = frame.drop_duplicates().copy()
        return frame, {'removed_rows': before - len(frame), 'affected_rows': before - len(frame)}
    if operation == 'normalize_columns':
        old = frame.columns.tolist()
        frame.columns = [str(column).strip().lower().replace(' ', '_') for column in frame.columns]
        return frame, {'renamed': dict(zip(old, frame.columns)), 'affected_rows': 0}
    if operation == 'parse_dates':
        changed = []
        for column in frame.columns:
            if any(word in str(column).lower() for word in ('date', 'time', 'month', 'year')):
                parsed = pd.to_datetime(frame[column], errors='coerce')
                if parsed.notna().any(): frame[column] = parsed; changed.append(column)
        return frame, {'columns': changed, 'affected_rows': before}
    raise ValueError('Unsupported transformation.')
