from __future__ import annotations

from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app import store
from backend.app.auth import current_user_id, issue_access_token
from backend.app.config import get_settings
from backend.app.config import Settings
from backend.app.db_models import Base


@pytest.fixture
def isolated_store(tmp_path, monkeypatch):
    engine = create_engine(f'sqlite:///{tmp_path / "pivot.db"}')
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(store, '_session', factory)
    return store


@contextmanager
def user_scope(user_id: str):
    token = current_user_id.set(user_id)
    try:
        yield
    finally:
        current_user_id.reset(token)


def create_user(google_id: str, email: str) -> dict:
    return store.upsert_google_user(google_id, email, google_id.title(), None)


def create_owned_resources(owner: dict) -> tuple[str, str, str]:
    with user_scope(owner['id']):
        dataset_id = store.create_dataset('private.csv', 'users/test/datasets/test/source.csv')
        store.finish_dataset(dataset_id, {'quality_score': 100})
        store.add_chunks(dataset_id, 'private.csv', ['private context'])
        store.add_version(dataset_id, 'cleaned', '{}')
        transformation_id = store.create_transformation(dataset_id, 'trim_text', 'preview.csv', {'affected_rows': 1})
        report_id = store.add_report(dataset_id, 'Private report', 'md', 'private.md')
    return dataset_id, transformation_id, report_id


def test_all_dataset_resources_are_scoped_to_the_authenticated_owner(isolated_store):
    owner = create_user('owner', 'owner@example.test')
    intruder = create_user('intruder', 'intruder@example.test')
    dataset_id, transformation_id, report_id = create_owned_resources(owner)

    with user_scope(owner['id']):
        dataset = store.get_dataset(dataset_id)
        assert dataset and len(dataset['versions']) == 2
        assert store.chunks_for(dataset_id)[0]['content'] == 'private context'
        assert len(store.events_for(dataset_id)) >= 3
        assert store.get_transformation(transformation_id)['id'] == transformation_id
        assert store.reports_for(dataset_id)[0]['id'] == report_id

    with user_scope(intruder['id']):
        assert store.get_dataset(dataset_id) is None
        assert store.get_transformation(transformation_id) is None
        with pytest.raises(LookupError):
            store.chunks_for(dataset_id)
        with pytest.raises(LookupError):
            store.events_for(dataset_id)
        with pytest.raises(LookupError):
            store.reports_for(dataset_id)
        with pytest.raises(LookupError):
            store.activate_dataset_version(dataset_id, 'other.csv', {'quality_score': 0})
        store.resolve_transformation(transformation_id, 'approved')

    with user_scope(owner['id']):
        assert store.get_transformation(transformation_id)['status'] == 'pending'


def test_private_api_routes_hide_cross_user_resources(isolated_store, monkeypatch):
    monkeypatch.setenv('JWT_SECRET', 'test-jwt-secret-that-is-long-enough')
    monkeypatch.setenv('GOOGLE_CLIENT_ID', 'test-client')
    monkeypatch.setenv('GOOGLE_CLIENT_SECRET', 'test-secret')
    get_settings.cache_clear()
    owner = create_user('api-owner', 'api-owner@example.test')
    intruder = create_user('api-intruder', 'api-intruder@example.test')
    dataset_id, _, _ = create_owned_resources(owner)

    from backend.app.main import app

    client = TestClient(app)
    assert client.get(f'/api/datasets/{dataset_id}').status_code == 401
    owner_response = client.get(f'/api/datasets/{dataset_id}', headers={'Authorization': f"Bearer {issue_access_token(owner['id'])}"})
    assert owner_response.status_code == 200
    intruder_response = client.get(f'/api/datasets/{dataset_id}', headers={'Authorization': f"Bearer {issue_access_token(intruder['id'])}"})
    assert intruder_response.status_code == 404


def test_business_context_is_attached_only_to_the_dataset_owner(isolated_store, monkeypatch):
    monkeypatch.setenv('JWT_SECRET', 'test-jwt-secret-that-is-long-enough')
    monkeypatch.setenv('GOOGLE_CLIENT_ID', 'test-client')
    monkeypatch.setenv('GOOGLE_CLIENT_SECRET', 'test-secret')
    get_settings.cache_clear()
    owner = create_user('context-owner', 'context-owner@example.test')
    dataset_id, _, _ = create_owned_resources(owner)

    from backend.app.main import app

    client = TestClient(app)
    response = client.post(
        f'/api/datasets/{dataset_id}/context',
        headers={'Authorization': f"Bearer {issue_access_token(owner['id'])}"},
        files={'file': ('glossary.md', b'Active customer means an order in the last 45 days.', 'text/markdown')},
    )
    assert response.status_code == 200
    assert response.json()['chunks'] == 1
    with user_scope(owner['id']):
        assert any('Active customer' in item['content'] for item in store.chunks_for(dataset_id))


def test_dataset_upload_uses_a_closed_temporary_file_on_windows(isolated_store, monkeypatch, tmp_path):
    monkeypatch.setenv('JWT_SECRET', 'test-jwt-secret-that-is-long-enough')
    monkeypatch.setenv('GOOGLE_CLIENT_ID', 'test-client')
    monkeypatch.setenv('GOOGLE_CLIENT_SECRET', 'test-secret')
    monkeypatch.setenv('STORAGE_BACKEND', 'local')
    monkeypatch.setenv('LOCAL_STORAGE_PATH', str(tmp_path / 'files'))
    get_settings.cache_clear()
    owner = create_user('upload-owner', 'upload@example.test')

    from backend.app.main import app

    client = TestClient(app)
    response = client.post(
        '/api/datasets',
        headers={'Authorization': f"Bearer {issue_access_token(owner['id'])}"},
        files={'file': ('sales.csv', b'value\n1\n2\n', 'text/csv')},
    )
    assert response.status_code == 200
    assert response.json()['rows'] == 2


def test_security_config_rejects_weak_jwt_secret():
    with pytest.raises(ValueError):
        Settings(jwt_secret='too-short').validate_auth_security()
    with pytest.raises(ValueError):
        Settings(jwt_secret='replace-with-a-long-random-secret-value').validate_auth_security()


def test_api_rejects_untrusted_origin_and_sets_security_headers(isolated_store, monkeypatch):
    monkeypatch.setenv('JWT_SECRET', 'test-jwt-secret-that-is-long-enough')
    monkeypatch.setenv('GOOGLE_CLIENT_ID', 'test-client')
    monkeypatch.setenv('GOOGLE_CLIENT_SECRET', 'test-secret')
    get_settings.cache_clear()
    owner = create_user('origin-owner', 'origin-owner@example.test')
    dataset_id, _, _ = create_owned_resources(owner)

    from backend.app.main import app

    client = TestClient(app)
    health = client.get('/health')
    assert health.headers['x-content-type-options'] == 'nosniff'
    response = client.post(
        f'/api/datasets/{dataset_id}/autopilot',
        headers={'Authorization': f"Bearer {issue_access_token(owner['id'])}", 'Origin': 'https://attacker.example', 'Cookie': 'pivot_access=present'},
    )
    assert response.status_code == 403
