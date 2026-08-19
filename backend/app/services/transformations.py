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
    source_frame = read_dataset_source(dataset)
    transformed_frame, metrics = apply(source_frame, operation)
    preview_metrics = preview_metrics_for(source_frame, transformed_frame, metrics)

    preview_path = save_preview(dataset, transformed_frame)
    transformation_id = create_transformation(dataset['id'], operation, preview_path, preview_metrics)

    return preview_response(transformation_id, operation, source_frame, transformed_frame, preview_metrics)


def approve(dataset: dict[str, Any], transformation_id: str) -> dict[str, Any]:
    transformation = pending(dataset['id'], transformation_id)
    cleaned_frame = load_preview(transformation['preview_path'])
    version = save_version(dataset, cleaned_frame, transformation)

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
    is_pending_for_dataset = (
        transformation
        and transformation['dataset_id'] == dataset_id
        and transformation['status'] == 'pending'
    )
    if not is_pending_for_dataset:
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
    detail = version_detail(output_path, transformation['metrics'], profile)
    operation = f'executed:{transformation["operation"]}'
    version_id = add_version(dataset['id'], operation, json.dumps(detail))

    activate_dataset_version(dataset['id'], output_path, profile)

    return version_response(version_number, version_id, output_path, transformation['metrics'], profile)


def preview_response(transformation_id: str, operation: str, before: pd.DataFrame, after: pd.DataFrame, metrics: dict[str, Any]) -> dict[str, Any]:
    before_preview = frame_preview(before)
    after_preview = frame_preview(after)
    return {
        'id': transformation_id,
        'operation': operation,
        'metrics': metrics,
        'rows_before': len(before),
        'rows_after': len(after),
        'before': frame_response(before, before_preview),
        'after': frame_response(after, after_preview),
        'before_preview': before_preview,
        'after_preview': after_preview,
        'source_unchanged': True,
    }


def preview_metrics_for(before: pd.DataFrame, after: pd.DataFrame, metrics: dict[str, Any]) -> dict[str, Any]:
    return {**metrics, 'rows_before': len(before), 'rows_after': len(after)}


def save_preview(dataset: dict[str, Any], frame: pd.DataFrame) -> str:
    return save_frame(dataset, frame, f'preview-{uuid4().hex}')


def version_detail(output_path: str, metrics: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    return {
        'output': output_path,
        'metrics': metrics,
        'profile': profile,
        'source_unchanged': True,
    }


def version_response(version_number: int, version_id: str, output_path: str, metrics: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    return {
        'ok': True,
        'version': version_number,
        'version_id': version_id,
        'rows_before': metrics.get('rows_before'),
        'rows_after': metrics.get('rows_after'),
        'metrics': metrics,
        'output': str(output_path),
        'profile': profile,
        'source_unchanged': True,
    }


def frame_response(frame: pd.DataFrame, preview: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        'rows': len(frame),
        'columns': [str(column) for column in frame.columns],
        'preview': preview,
    }


def frame_preview(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return json.loads(frame.head(8).astype(object).where(frame.head(8).notna(), None).to_json(orient='records'))
