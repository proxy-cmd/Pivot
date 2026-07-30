from __future__ import annotations

import shutil
import os
from contextlib import contextmanager
from pathlib import Path
from tempfile import mkstemp
from typing import BinaryIO, Iterator

from .config import get_settings


class Storage:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.local = self.settings.storage_backend == 'local'
        self.root = Path(self.settings.local_storage_path)
        self.client = None
        if not self.local:
            import boto3
            self.client = boto3.client(
                's3', endpoint_url=self.settings.storage_endpoint_url or None,
                region_name=self.settings.storage_region or None,
                aws_access_key_id=self.settings.storage_access_key,
                aws_secret_access_key=self.settings.storage_secret_key,
            )

    def key(self, user_id: str, dataset_id: str, name: str, suffix: str) -> str:
        return f'users/{user_id}/datasets/{dataset_id}/{name}{suffix}'

    def upload_file(self, source: Path, key: str) -> None:
        if self.local:
            target = self.root / key
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            return
        self.client.upload_file(str(source), self.settings.storage_bucket, key)

    @contextmanager
    def local_file(self, key: str) -> Iterator[Path]:
        if self.local:
            yield self.root / key
            return
        suffix = Path(key).suffix
        descriptor, name = mkstemp(suffix=suffix)
        os.close(descriptor)
        path = Path(name)
        try:
            self.client.download_file(self.settings.storage_bucket, key, str(path))
            yield path
        finally:
            path.unlink(missing_ok=True)

    def stream(self, key: str, chunk_size: int = 64 * 1024) -> Iterator[bytes]:
        if self.local:
            with (self.root / key).open('rb') as handle:
                while chunk := handle.read(chunk_size):
                    yield chunk
            return
        body = self.client.get_object(Bucket=self.settings.storage_bucket, Key=key)['Body']
        try:
            while chunk := body.read(chunk_size):
                yield chunk
        finally:
            body.close()

    def delete(self, key: str) -> None:
        if self.local:
            (self.root / key).unlink(missing_ok=True)
        else:
            self.client.delete_object(Bucket=self.settings.storage_bucket, Key=key)


def get_storage() -> Storage:
    return Storage()
