from pathlib import Path

import pytest

from backend.app.config import Settings
from backend.app.storage import Storage


def test_production_requires_object_storage():
    settings = Settings(
        app_env='production',
        database_url='postgresql+psycopg://user:pass@db/pivot',
        google_client_id='client', google_client_secret='secret',
        jwt_secret='a' * 32, cookie_secure=True,
        frontend_url='https://app.example.test',
        google_redirect_uri='https://api.example.test/api/auth/google/callback',
        cors_origins='https://app.example.test',
    )
    with pytest.raises(ValueError, match='STORAGE_BACKEND=s3'):
        settings.validate_production()


def test_local_storage_keeps_keys_inside_its_root(tmp_path, monkeypatch):
    monkeypatch.setenv('STORAGE_BACKEND', 'local')
    monkeypatch.setenv('LOCAL_STORAGE_PATH', str(tmp_path))
    from backend.app.config import get_settings
    get_settings.cache_clear()
    source = tmp_path / 'source.csv'
    source.write_text('value\n1\n', encoding='utf-8')
    storage = Storage()
    key = storage.key('owner', 'dataset', 'source', '.csv')
    storage.upload_file(source, key)
    with storage.local_file(key) as saved:
        assert saved == tmp_path / Path(key)
        assert saved.read_text(encoding='utf-8') == 'value\n1\n'
    get_settings.cache_clear()
