from __future__ import annotations

import shutil
import os
from contextlib import contextmanager
from pathlib import Path
from tempfile import mkstemp
from typing import Iterator

from ..core.config import get_settings


class Storage:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.local = self.settings.storage_backend == 'local'
        self.root = Path(self.settings.local_storage_path)
        self.client = None if self.local else self.create_s3_client()

    def create_s3_client(self):
        import boto3

        return boto3.client(
            's3',
            endpoint_url=self.settings.storage_endpoint_url or None,
            region_name=self.settings.storage_region or None,
            aws_access_key_id=self.settings.storage_access_key,
            aws_secret_access_key=self.settings.storage_secret_key,
        )

    def key(self, user_id: str, dataset_id: str, name: str, suffix: str) -> str:
        return f'users/{user_id}/datasets/{dataset_id}/{name}{suffix}'

    def upload_file(self, source: Path, key: str) -> None:
        if self.local:
            self.upload_local_file(source, key)
            return

        self.s3_client.upload_file(str(source), self.settings.storage_bucket, key)

    def upload_local_file(self, source: Path, key: str) -> None:
        target = self.root / key
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)

    @contextmanager
    def local_file(self, key: str) -> Iterator[Path]:
        if self.local:
            yield self.root / key
            return

        with self.download_s3_file(key) as path:
            yield path

    @contextmanager
    def download_s3_file(self, key: str) -> Iterator[Path]:
        suffix = Path(key).suffix
        descriptor, name = mkstemp(suffix=suffix)
        os.close(descriptor)
        path = Path(name)
        try:
            self.s3_client.download_file(self.settings.storage_bucket, key, str(path))
            yield path
        finally:
            path.unlink(missing_ok=True)

    def stream(self, key: str, chunk_size: int = 64 * 1024) -> Iterator[bytes]:
        if self.local:
            yield from self.stream_local_file(key, chunk_size)
            return

        yield from self.stream_s3_file(key, chunk_size)

    def stream_local_file(self, key: str, chunk_size: int) -> Iterator[bytes]:
        with (self.root / key).open('rb') as handle:
            while chunk := handle.read(chunk_size):
                yield chunk

    def stream_s3_file(self, key: str, chunk_size: int) -> Iterator[bytes]:
        body = self.s3_client.get_object(Bucket=self.settings.storage_bucket, Key=key)['Body']
        try:
            while chunk := body.read(chunk_size):
                yield chunk
        finally:
            body.close()

    def delete(self, key: str) -> None:
        if self.local:
            (self.root / key).unlink(missing_ok=True)
            return

        self.s3_client.delete_object(Bucket=self.settings.storage_bucket, Key=key)

    @property
    def s3_client(self):
        if self.client is None:
            raise RuntimeError('S3 storage client is not configured.')
        return self.client


def get_storage() -> Storage:
    return Storage()
