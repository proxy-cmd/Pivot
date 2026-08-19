"""Preview, approve, and reject versioned dataset transformations."""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

import pandas as pd

from ..dataset_io import profile_payload, read_dataset_source, save_frame
from ..pipeline import apply
from ..storage import get_storage
from ..store import add_version, activate_dataset_version, create_transformation, get_transformation, resolve_transformation

SUPPORTED_OPERATIONS = frozenset({'trim_text', 'remove_duplicates', 'normalize_columns', 'parse_dates', 'fill_missing', 'remove_outliers', 'standardize_format'})


class TransformationError(ValueError):
    """Raised when a transformation cannot be completed safely."""


def preview(dataset: dict[str, Any], operation: str) -> dict[str, Any]:
    validate_operation(operation)
    before = read_dataset_source(dataset)
    after, metrics = apply(before.copy(), operation)
    metrics = {**metrics, 'rows_before': len(before), 'rows_after': len(after)}
    preview_path = save_frame(dataset, after, f'preview-{uuid4().hex}')
    transformation_id = create_transformation(dataset['id'], operation, preview_path, metrics)
    return preview_response(transformation_id, operation, before, after, metrics)


def approve(dataset: dict[str, Any], transformation_id: str) -> dict[str, Any]:
    transformation = pending(dataset['id'], transformation_id)
    cleaned = load_preview(transformation['preview_path'])
    version = save_version(dataset, cleaned, transformation)
    resolve_transformation(transformation_id, 'approved')
    get_storage().delete(transformation['preview_path'])
    return version


def reject(dataset_id: str, transformation_id: str) -> dict[str, Any]:
    transformation = pending(dataset_id, transformation_id)
    get_storage().delete(transformation['preview_path'])
    resolve_transformation(transformation_id, 'rejected')
    return {'ok': True, 'message': 'Transformation rejected; the source remains unchanged.'}


def validate_operation(operation: str) -> None:
    if operation not in SUPPORTED_OPERATIONS:
        raise TransformationError('Unsupported transformation.')


def pending(dataset_id: str, transformation_id: str) -> dict[str, Any]:
    transformation = get_transformation(transformation_id)
    if not transformation or transformation['dataset_id'] != dataset_id or transformation['status'] != 'pending':
        raise TransformationError('Pending transformation preview not found.')
    return transformation


def load_preview(path: str) -> pd.DataFrame:
    try:
        with get_storage().local_file(path) as preview_file:
            return pd.read_csv(preview_file)
    except Exception as error:
        raise TransformationError('Transformation preview is unavailable.') from error


def save_version(dataset: dict[str, Any], cleaned: pd.DataFrame, transformation: dict[str, Any]) -> dict[str, Any]:
    version_number = len(dataset['versions'])
    output_path = save_frame(dataset, cleaned, f'version-{version_number}')
    profile = profile_payload(cleaned, dataset['name'], dataset['id'])
    detail = {'output': output_path, 'metrics': transformation['metrics'], 'profile': profile, 'source_unchanged': True}
    version_id = add_version(dataset['id'], f'executed:{transformation["operation"]}', json.dumps(detail))
    activate_dataset_version(dataset['id'], output_path, profile)
    return {'ok': True, 'version': version_number, 'version_id': version_id, 'rows_before': transformation['metrics'].get('rows_before'), 'rows_after': transformation['metrics'].get('rows_after'), 'metrics': transformation['metrics'], 'output': str(output_path), 'profile': profile, 'source_unchanged': True}


def preview_response(transformation_id: str, operation: str, before: pd.DataFrame, after: pd.DataFrame, metrics: dict[str, Any]) -> dict[str, Any]:
    before_preview = frame_preview(before)
    after_preview = frame_preview(after)
    return {'id': transformation_id, 'operation': operation, 'metrics': metrics, 'rows_before': len(before), 'rows_after': len(after), 'before': {'rows': len(before), 'columns': [str(column) for column in before.columns], 'preview': before_preview}, 'after': {'rows': len(after), 'columns': [str(column) for column in after.columns], 'preview': after_preview}, 'before_preview': before_preview, 'after_preview': after_preview, 'source_unchanged': True}


def frame_preview(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return json.loads(frame.head(8).astype(object).where(frame.head(8).notna(), None).to_json(orient='records'))
