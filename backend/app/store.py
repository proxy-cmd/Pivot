from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ROOT = PROJECT_ROOT / 'data'
FILES = ROOT / 'files'
DB = ROOT / 'pivot.db'


def absolute_path(value: str | None) -> str | None:
    if not value:
        return value
    path = Path(value)
    return str(path if path.is_absolute() else PROJECT_ROOT / path)


def connect():
    ROOT.mkdir(exist_ok=True)
    FILES.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, google_id TEXT NOT NULL UNIQUE, email TEXT NOT NULL UNIQUE, full_name TEXT NOT NULL, avatar_url TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP, last_login TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS refresh_sessions (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, token_hash TEXT NOT NULL UNIQUE, expires_at TEXT NOT NULL, user_agent TEXT, ip_address TEXT, parent_id TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP, revoked_at TEXT, FOREIGN KEY(user_id) REFERENCES users(id));
    CREATE TABLE IF NOT EXISTS datasets (id TEXT PRIMARY KEY, owner_user_id TEXT, name TEXT, source_path TEXT, active_path TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP, profile TEXT, status TEXT, FOREIGN KEY(owner_user_id) REFERENCES users(id));
    CREATE TABLE IF NOT EXISTS versions (id TEXT PRIMARY KEY, dataset_id TEXT, number INTEGER, parent_id TEXT, operation TEXT, detail TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS chunks (id TEXT PRIMARY KEY, dataset_id TEXT, source TEXT, content TEXT, metadata TEXT);
    CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, dataset_id TEXT, kind TEXT, message TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS transformations (id TEXT PRIMARY KEY, dataset_id TEXT, operation TEXT, status TEXT, preview_path TEXT, metrics TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP, resolved_at TEXT);
    CREATE TABLE IF NOT EXISTS reports (id TEXT PRIMARY KEY, dataset_id TEXT, title TEXT, format TEXT, path TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    ''')
    columns = {row['name'] for row in conn.execute('PRAGMA table_info(datasets)')}
    if 'active_path' not in columns:
        conn.execute('ALTER TABLE datasets ADD COLUMN active_path TEXT')
        conn.execute('UPDATE datasets SET active_path=source_path WHERE active_path IS NULL')
    if 'owner_user_id' not in columns:
        conn.execute('ALTER TABLE datasets ADD COLUMN owner_user_id TEXT')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_datasets_owner ON datasets(owner_user_id)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_refresh_sessions_token ON refresh_sessions(token_hash)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_refresh_sessions_user ON refresh_sessions(user_id)')
    return conn


def _current_user_id() -> str:
    from .auth import current_user_id
    user_id = current_user_id.get()
    if not user_id:
        raise RuntimeError('A user context is required for data access.')
    return user_id


def get_user(user_id: str):
    with connect() as db:
        row = db.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
        return dict(row) if row else None


def upsert_google_user(google_id: str, email: str, full_name: str, avatar_url: str | None):
    now = datetime.now(UTC).isoformat()
    with connect() as db:
        existing = db.execute('SELECT id FROM users WHERE google_id=?', (google_id,)).fetchone()
        if existing:
            db.execute('UPDATE users SET email=?, full_name=?, avatar_url=?, updated_at=?, last_login=? WHERE id=?', (email.lower(), full_name, avatar_url, now, now, existing['id']))
            user_id = existing['id']
        else:
            user_id = uuid4().hex
            db.execute('INSERT INTO users(id,google_id,email,full_name,avatar_url,last_login) VALUES(?,?,?,?,?,?)', (user_id, google_id, email.lower(), full_name, avatar_url, now))
    return get_user(user_id)


def create_refresh_session(user_id: str, token_hash: str, expires_at: str, user_agent: str, ip_address: str | None, parent_id: str | None = None):
    with connect() as db:
        db.execute('INSERT INTO refresh_sessions(id,user_id,token_hash,expires_at,user_agent,ip_address,parent_id) VALUES(?,?,?,?,?,?,?)', (uuid4().hex, user_id, token_hash, expires_at, user_agent, ip_address, parent_id))


def consume_refresh_session(token_hash: str):
    now = datetime.now(UTC).isoformat()
    with connect() as db:
        row = db.execute('SELECT s.*, u.id AS user_id, u.google_id, u.email, u.full_name, u.avatar_url, u.created_at AS user_created_at, u.updated_at AS user_updated_at, u.last_login FROM refresh_sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.revoked_at IS NULL AND s.expires_at>?', (token_hash, now)).fetchone()
        if not row:
            return None
        db.execute('UPDATE refresh_sessions SET revoked_at=? WHERE id=? AND revoked_at IS NULL', (now, row['id']))
        if db.total_changes != 1:
            return None
        item = dict(row)
        item['user'] = {'id': item['user_id'], 'google_id': item['google_id'], 'email': item['email'], 'full_name': item['full_name'], 'avatar_url': item['avatar_url'], 'created_at': item['user_created_at'], 'updated_at': item['user_updated_at'], 'last_login': item['last_login']}
        return item


def revoke_refresh_session(token_hash: str):
    with connect() as db:
        db.execute('UPDATE refresh_sessions SET revoked_at=? WHERE token_hash=? AND revoked_at IS NULL', (datetime.now(UTC).isoformat(), token_hash))


def event(dataset_id: str, kind: str, message: str):
    with connect() as db:
        db.execute('INSERT INTO events(dataset_id, kind, message) VALUES(?,?,?)', (dataset_id, kind, message))


def create_dataset(name: str, suffix: str, raw: bytes) -> str:
    ROOT.mkdir(exist_ok=True)
    FILES.mkdir(exist_ok=True)
    dataset_id = uuid4().hex
    path = FILES / f'{dataset_id}{suffix}'
    path.write_bytes(raw)
    with connect() as db:
        db.execute('INSERT INTO datasets(id,owner_user_id,name,source_path,active_path,status) VALUES(?,?,?,?,?,?)', (dataset_id, _current_user_id(), name, str(path), str(path), 'processing'))
    event(dataset_id, 'ingest', 'Source file stored unchanged as version 0.')
    return dataset_id


def finish_dataset(dataset_id: str, profile: dict):
    with connect() as db:
        db.execute('UPDATE datasets SET profile=?, status=? WHERE id=?', (json.dumps(profile), 'ready', dataset_id))
        db.execute('INSERT INTO versions(id,dataset_id,number,operation,detail) VALUES(?,?,?,?,?)', (uuid4().hex, dataset_id, 0, 'source', 'Original source preserved; no changes applied.'))
    event(dataset_id, 'profile', f"Profile complete: data quality {profile['quality_score']}/100.")
    event(dataset_id, 'ready', 'Dataset is ready for analysis and grounded chat.')


def get_dataset(dataset_id: str):
    with connect() as db:
        row = db.execute('SELECT * FROM datasets WHERE id=? AND owner_user_id=?', (dataset_id, _current_user_id())).fetchone()
        if not row: return None
        item = dict(row); item['source_path'] = absolute_path(item.get('source_path')); item['active_path'] = absolute_path(item.get('active_path')); item['profile'] = json.loads(item['profile']) if item['profile'] else None
        profile = item.get('profile') or {}
        schema = profile.get('schema') or {}
        date_words = ('date', 'time', 'month', 'year', 'created', 'ordered')
        needs_profile_repair = bool(set(schema.get('date_columns', [])) & set(schema.get('numeric_columns', []))) or any(any(word in str(column).lower() for word in date_words) for column in schema.get('numeric_columns', []))
        if needs_profile_repair:
            try:
                import pandas as pd
                from .analytics import prepare_frame, profile_frame
                source = Path(item['active_path'] or item['source_path'])
                if source.suffix.lower() in {'.xlsx', '.xls'}:
                    frame = pd.read_excel(source)
                elif source.suffix.lower() == '.json':
                    frame = pd.read_json(source)
                elif source.suffix.lower() == '.parquet':
                    frame = pd.read_parquet(source)
                else:
                    frame = pd.read_csv(source)
                repaired = profile_frame(prepare_frame(frame), item['name'])
                repaired['columns_list'] = [str(column) for column in prepare_frame(frame).columns]
                repaired['preview'] = json.loads(prepare_frame(frame).head(8).fillna('').to_json(orient='records', date_format='iso'))
                repaired['recommendations'] = profile.get('recommendations', [])
                with connect() as update_db:
                    update_db.execute('UPDATE datasets SET profile=? WHERE id=?', (json.dumps(repaired), dataset_id))
                item['profile'] = repaired
            except Exception:
                pass
        item['versions'] = [dict(v) for v in db.execute('SELECT * FROM versions WHERE dataset_id=? ORDER BY number', (dataset_id,))]
        item['active_version'] = 0
        for version in item['versions']:
            try:
                if json.loads(version['detail']).get('output') == item.get('active_path'):
                    item['active_version'] = version['number']
            except (TypeError, json.JSONDecodeError):
                continue
        item['pending_transformations'] = [dict(v) for v in db.execute('SELECT * FROM transformations WHERE dataset_id=? AND status=? ORDER BY created_at DESC', (dataset_id, 'pending'))]
        return item


def add_chunks(dataset_id: str, source: str, chunks: list[str]):
    with connect() as db:
        db.executemany('INSERT INTO chunks(id,dataset_id,source,content,metadata) VALUES(?,?,?,?,?)', [(uuid4().hex, dataset_id, source, chunk, '{}') for chunk in chunks])


def chunks_for(dataset_id: str):
    with connect() as db:
        return [dict(row) for row in db.execute('SELECT source,content,metadata FROM chunks WHERE dataset_id=?', (dataset_id,))]


def events_for(dataset_id: str):
    with connect() as db:
        return [dict(row) for row in db.execute('SELECT kind,message,created_at FROM events WHERE dataset_id=? ORDER BY id DESC LIMIT 20', (dataset_id,))]


def add_version(dataset_id: str, operation: str, detail: str):
    current = get_dataset(dataset_id)
    number = len(current['versions']) if current else 0
    parent_id = current['versions'][-1]['id'] if current and current['versions'] else None
    version_id = uuid4().hex
    with connect() as db:
        db.execute('INSERT INTO versions(id,dataset_id,number,parent_id,operation,detail) VALUES(?,?,?,?,?,?)', (version_id, dataset_id, number, parent_id, operation, detail))
    event(dataset_id, 'lineage', f'Version {number} created: {operation}.')
    return version_id


def activate_dataset_version(dataset_id: str, path: str, profile: dict):
    with connect() as db:
        db.execute('UPDATE datasets SET active_path=?, profile=?, status=? WHERE id=?', (path, json.dumps(profile), 'ready', dataset_id))


def create_transformation(dataset_id: str, operation: str, preview_path: str, metrics: dict) -> str:
    transformation_id = uuid4().hex
    with connect() as db:
        db.execute('INSERT INTO transformations(id,dataset_id,operation,status,preview_path,metrics) VALUES(?,?,?,?,?,?)', (transformation_id, dataset_id, operation, 'pending', preview_path, json.dumps(metrics)))
    event(dataset_id, 'cleaning', f'Preview created for {operation}; awaiting approval.')
    return transformation_id


def get_transformation(transformation_id: str):
    with connect() as db:
        row = db.execute('SELECT * FROM transformations WHERE id=?', (transformation_id,)).fetchone()
        if not row:
            return None
        item = dict(row)
        item['metrics'] = json.loads(item['metrics'] or '{}')
        return item


def resolve_transformation(transformation_id: str, status: str):
    with connect() as db:
        db.execute('UPDATE transformations SET status=?, resolved_at=CURRENT_TIMESTAMP WHERE id=?', (status, transformation_id))


def add_report(dataset_id: str, title: str, format: str, path: str):
    report_id = uuid4().hex
    with connect() as db:
        db.execute('INSERT INTO reports(id,dataset_id,title,format,path) VALUES(?,?,?,?,?)', (report_id, dataset_id, title, format, path))
    event(dataset_id, 'report', f'Report exported: {title} ({format}).')
    return report_id


def reports_for(dataset_id: str):
    with connect() as db:
        return [dict(row) for row in db.execute('SELECT * FROM reports WHERE dataset_id=? ORDER BY created_at DESC', (dataset_id,))]
