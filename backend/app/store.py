from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .database import get_session_factory
from .db.models import Chunk, Dataset, DatasetEvent, RefreshSession, Report, Transformation, User, Version

def _session() -> Session:
    return get_session_factory()()


def _current_user_id() -> str:
    from .auth import current_user_id
    user_id = current_user_id.get()
    if not user_id:
        raise RuntimeError('A user context is required for data access.')
    return user_id


def _owned_dataset(session: Session, dataset_id: str) -> Dataset:
    dataset = session.scalar(select(Dataset).where(Dataset.id == dataset_id, Dataset.owner_user_id == _current_user_id()))
    if not dataset:
        raise LookupError('Dataset not found.')
    return dataset


def _user_payload(user: User) -> dict:
    return {'id': user.id, 'google_id': user.google_id, 'email': user.email, 'full_name': user.full_name, 'avatar_url': user.avatar_url, 'created_at': user.created_at, 'updated_at': user.updated_at, 'last_login': user.last_login}


def get_user(user_id: str):
    with _session() as session:
        user = session.get(User, user_id)
        return _user_payload(user) if user else None


def upsert_google_user(google_id: str, email: str, full_name: str, avatar_url: str | None):
    now = datetime.now(UTC)
    with _session() as session:
        user = session.scalar(select(User).where(User.google_id == google_id))
        if user:
            user.email, user.full_name, user.avatar_url, user.updated_at, user.last_login = email.lower(), full_name, avatar_url, now, now
        else:
            user = User(id=uuid4().hex, google_id=google_id, email=email.lower(), full_name=full_name, avatar_url=avatar_url, last_login=now)
            session.add(user)
        session.commit()
        return _user_payload(user)


def create_refresh_session(user_id: str, token_hash: str, expires_at: str, user_agent: str, ip_address: str | None, parent_id: str | None = None):
    with _session() as session:
        session.add(RefreshSession(id=uuid4().hex, user_id=user_id, token_hash=token_hash, expires_at=datetime.fromisoformat(expires_at), user_agent=user_agent, ip_address=ip_address, parent_id=parent_id))
        session.commit()


def consume_refresh_session(token_hash: str):
    with _session() as session:
        row = session.scalar(select(RefreshSession).options(selectinload(RefreshSession.user)).where(RefreshSession.token_hash == token_hash, RefreshSession.revoked_at.is_(None), RefreshSession.expires_at > datetime.now(UTC)).with_for_update())
        if not row:
            return None
        row.revoked_at = datetime.now(UTC)
        session.commit()
        return {'id': row.id, 'user': _user_payload(row.user)}


def revoke_refresh_session(token_hash: str):
    with _session() as session:
        row = session.scalar(select(RefreshSession).where(RefreshSession.token_hash == token_hash, RefreshSession.revoked_at.is_(None)))
        if row:
            row.revoked_at = datetime.now(UTC)
            session.commit()


def event(dataset_id: str, kind: str, message: str):
    with _session() as session:
        dataset = _owned_dataset(session, dataset_id)
        session.add(DatasetEvent(dataset_id=dataset.id, owner_user_id=dataset.owner_user_id, kind=kind, message=message))
        session.commit()


def create_dataset(name: str, source_key: str, dataset_id: str | None = None) -> str:
    dataset_id = dataset_id or uuid4().hex
    with _session() as session:
        session.add(Dataset(id=dataset_id, owner_user_id=_current_user_id(), name=name, source_path=source_key, active_path=source_key, status='processing'))
        session.commit()
    event(dataset_id, 'ingest', 'Source file stored unchanged as version 0.')
    return dataset_id


def finish_dataset(dataset_id: str, profile: dict):
    with _session() as session:
        dataset = _owned_dataset(session, dataset_id)
        dataset.profile, dataset.status = json.dumps(profile), 'ready'
        session.add(Version(id=uuid4().hex, dataset_id=dataset.id, owner_user_id=dataset.owner_user_id, number=0, operation='source', detail='Original source preserved; no changes applied.'))
        session.commit()
    event(dataset_id, 'profile', f"Profile complete: data quality {profile['quality_score']}/100.")
    event(dataset_id, 'ready', 'Dataset is ready for analysis and grounded chat.')


def _dataset_payload(dataset: Dataset) -> dict:
    payload = dataset_summary(dataset)
    payload['versions'] = version_payloads(dataset.versions)
    payload['pending_transformations'] = pending_transformation_payloads(dataset.transformations)
    payload['active_version'] = active_version_number(payload['versions'], dataset.active_path)
    return payload


def dataset_summary(dataset: Dataset) -> dict:
    return {
        'id': dataset.id,
        'owner_user_id': dataset.owner_user_id,
        'name': dataset.name,
        'source_path': dataset.source_path,
        'active_path': dataset.active_path,
        'created_at': dataset.created_at,
        'profile': json.loads(dataset.profile) if dataset.profile else None,
        'status': dataset.status,
    }


def version_payloads(versions: list[Version]) -> list[dict]:
    return [version_payload(version) for version in sorted(versions, key=lambda version: version.number)]


def version_payload(version: Version) -> dict:
    return {
        'id': version.id,
        'dataset_id': version.dataset_id,
        'owner_user_id': version.owner_user_id,
        'number': version.number,
        'parent_id': version.parent_id,
        'operation': version.operation,
        'detail': version.detail,
        'created_at': version.created_at,
    }


def pending_transformation_payloads(transformations: list[Transformation]) -> list[dict]:
    pending = (entry for entry in transformations if entry.status == 'pending')
    ordered = sorted(pending, key=lambda entry: entry.created_at, reverse=True)
    return [transformation_payload(entry) for entry in ordered]


def transformation_payload(transformation: Transformation) -> dict:
    return {
        'id': transformation.id,
        'dataset_id': transformation.dataset_id,
        'owner_user_id': transformation.owner_user_id,
        'operation': transformation.operation,
        'status': transformation.status,
        'preview_path': transformation.preview_path,
        'metrics': json.loads(transformation.metrics or '{}'),
        'created_at': transformation.created_at,
        'resolved_at': transformation.resolved_at,
    }


def active_version_number(versions: list[dict], active_path: str) -> int:
    for version in versions:
        output_path = version_output_path(version['detail'])
        if output_path == active_path:
            return version['number']

    return 0


def version_output_path(detail: str) -> str | None:
    try:
        return json.loads(detail).get('output')
    except (TypeError, json.JSONDecodeError):
        return None


def get_dataset(dataset_id: str):
    with _session() as session:
        dataset = session.scalar(select(Dataset).options(selectinload(Dataset.versions), selectinload(Dataset.transformations)).where(Dataset.id == dataset_id, Dataset.owner_user_id == _current_user_id()))
        return _dataset_payload(dataset) if dataset else None


def add_chunks(dataset_id: str, source: str, chunks: list[str]):
    with _session() as session:
        dataset = _owned_dataset(session, dataset_id)
        session.add_all(Chunk(id=uuid4().hex, dataset_id=dataset.id, owner_user_id=dataset.owner_user_id, source=source, content=chunk, metadata_json='{}') for chunk in chunks)
        session.commit()


def chunks_for(dataset_id: str):
    with _session() as session:
        dataset = _owned_dataset(session, dataset_id)
        return [{'source': row.source, 'content': row.content, 'metadata': row.metadata_json} for row in session.scalars(select(Chunk).where(Chunk.dataset_id == dataset.id, Chunk.owner_user_id == dataset.owner_user_id)).all()]


def events_for(dataset_id: str):
    with _session() as session:
        dataset = _owned_dataset(session, dataset_id)
        return [{'kind': row.kind, 'message': row.message, 'created_at': row.created_at} for row in session.scalars(select(DatasetEvent).where(DatasetEvent.dataset_id == dataset.id, DatasetEvent.owner_user_id == dataset.owner_user_id).order_by(DatasetEvent.id.desc()).limit(20)).all()]


def add_version(dataset_id: str, operation: str, detail: str):
    with _session() as session:
        dataset = _owned_dataset(session, dataset_id)
        versions = session.scalars(select(Version).where(Version.dataset_id == dataset.id, Version.owner_user_id == dataset.owner_user_id).order_by(Version.number)).all()
        version = Version(id=uuid4().hex, dataset_id=dataset.id, owner_user_id=dataset.owner_user_id, number=len(versions), parent_id=versions[-1].id if versions else None, operation=operation, detail=detail)
        session.add(version)
        session.commit()
    event(dataset_id, 'lineage', f'Version {version.number} created: {operation}.')
    return version.id


def activate_dataset_version(dataset_id: str, path: str, profile: dict):
    with _session() as session:
        dataset = _owned_dataset(session, dataset_id)
        dataset.active_path, dataset.profile, dataset.status = path, json.dumps(profile), 'ready'
        session.commit()


def create_transformation(dataset_id: str, operation: str, preview_path: str, metrics: dict) -> str:
    with _session() as session:
        dataset = _owned_dataset(session, dataset_id)
        value = Transformation(id=uuid4().hex, dataset_id=dataset.id, owner_user_id=dataset.owner_user_id, operation=operation, status='pending', preview_path=preview_path, metrics=json.dumps(metrics))
        session.add(value)
        session.commit()
    event(dataset_id, 'cleaning', f'Preview created for {operation}; awaiting approval.')
    return value.id


def get_transformation(transformation_id: str):
    with _session() as session:
        value = session.scalar(select(Transformation).where(Transformation.id == transformation_id, Transformation.owner_user_id == _current_user_id()))
        if not value:
            return None
        return {'id': value.id, 'dataset_id': value.dataset_id, 'owner_user_id': value.owner_user_id, 'operation': value.operation, 'status': value.status, 'preview_path': value.preview_path, 'metrics': json.loads(value.metrics or '{}'), 'created_at': value.created_at, 'resolved_at': value.resolved_at}


def resolve_transformation(transformation_id: str, status: str):
    with _session() as session:
        value = session.scalar(select(Transformation).where(Transformation.id == transformation_id, Transformation.owner_user_id == _current_user_id()))
        if value:
            value.status, value.resolved_at = status, datetime.now(UTC)
            session.commit()


def add_report(dataset_id: str, title: str, format: str, path: str):
    with _session() as session:
        dataset = _owned_dataset(session, dataset_id)
        value = Report(id=uuid4().hex, dataset_id=dataset.id, owner_user_id=dataset.owner_user_id, title=title, format=format, path=path)
        session.add(value)
        session.commit()
    event(dataset_id, 'report', f'Report exported: {title} ({format}).')
    return value.id


def reports_for(dataset_id: str):
    with _session() as session:
        dataset = _owned_dataset(session, dataset_id)
        return [{'id': row.id, 'dataset_id': row.dataset_id, 'owner_user_id': row.owner_user_id, 'title': row.title, 'format': row.format, 'path': row.path, 'created_at': row.created_at} for row in session.scalars(select(Report).where(Report.dataset_id == dataset.id, Report.owner_user_id == dataset.owner_user_id).order_by(Report.created_at.desc())).all()]
