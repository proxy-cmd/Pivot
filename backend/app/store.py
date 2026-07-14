from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from uuid import uuid4

ROOT = Path('data')
FILES = ROOT / 'files'
DB = ROOT / 'pivot.db'


def connect():
    ROOT.mkdir(exist_ok=True); FILES.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS datasets (id TEXT PRIMARY KEY, name TEXT, source_path TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP, profile TEXT, status TEXT);
    CREATE TABLE IF NOT EXISTS versions (id TEXT PRIMARY KEY, dataset_id TEXT, number INTEGER, parent_id TEXT, operation TEXT, detail TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS chunks (id TEXT PRIMARY KEY, dataset_id TEXT, source TEXT, content TEXT, metadata TEXT);
    CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, dataset_id TEXT, kind TEXT, message TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    ''')
    return conn


def event(dataset_id: str, kind: str, message: str):
    with connect() as db:
        db.execute('INSERT INTO events(dataset_id, kind, message) VALUES(?,?,?)', (dataset_id, kind, message))


def create_dataset(name: str, suffix: str, raw: bytes) -> str:
    dataset_id = uuid4().hex
    path = FILES / f'{dataset_id}{suffix}'
    path.write_bytes(raw)
    with connect() as db:
        db.execute('INSERT INTO datasets(id,name,source_path,status) VALUES(?,?,?,?)', (dataset_id, name, str(path), 'processing'))
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
        row = db.execute('SELECT * FROM datasets WHERE id=?', (dataset_id,)).fetchone()
        if not row: return None
        item = dict(row); item['profile'] = json.loads(item['profile']) if item['profile'] else None
        item['versions'] = [dict(v) for v in db.execute('SELECT * FROM versions WHERE dataset_id=? ORDER BY number', (dataset_id,))]
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
    with connect() as db:
        db.execute('INSERT INTO versions(id,dataset_id,number,operation,detail) VALUES(?,?,?,?,?)', (uuid4().hex, dataset_id, number, operation, detail))
    event(dataset_id, 'lineage', f'Proposed transformation recorded: {operation}.')
