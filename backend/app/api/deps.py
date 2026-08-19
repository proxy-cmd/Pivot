"""Small dependencies shared by route modules."""

from fastapi import HTTPException

from ..store import get_dataset


def dataset_or_404(dataset_id: str) -> dict:
    """Return the caller-owned dataset or preserve the existing 404 contract."""
    dataset = get_dataset(dataset_id)
    if not dataset:
        raise HTTPException(404, 'Dataset session not found.')
    return dataset
