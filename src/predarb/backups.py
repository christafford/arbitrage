"""Verified SQLite online backup and restore into NEW paths. Source never migrates."""
from contextlib import closing
from datetime import datetime, timezone
from hashlib import sha256
import os
import re
from pathlib import Path
import sqlite3
import time
from shutil import disk_usage

from .validation import dumps, field, load_json, object_value, text_field, utc_time


def readonly(path):
    target = Path(path).resolve(strict=True)
    con = sqlite3.connect(target.as_uri() + '?mode=ro', uri=True, timeout=5)
    try:
        version = con.execute('PRAGMA user_version').fetchone()[0]
        if version > 8: raise ValueError('unsupported read-only database schema version ' + str(version))
        return con
    except BaseException:
        con.close()
        raise


def file_hash(path):
    result = sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def fingerprint(con):
    """Stable logical digest includes schema, all user rows and exact BLOB bytes."""
    if con.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
        raise ValueError('SQLite integrity check failed')
    if con.execute('PRAGMA foreign_key_check').fetchone() is not None:
        raise ValueError('SQLite foreign-key check failed')
    version = con.execute('PRAGMA user_version').fetchone()[0]
    if not 1 <= version <= 8:
        raise ValueError('unsupported backup schema')
    digest = sha256()
    counts = {}
    for name, sql in con.execute("SELECT name,sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
        digest.update(dumps([name, sql]).encode())
        count = 0
        quoted = '"' + name.replace('"', '""') + '"'
        for row in con.execute('SELECT * FROM ' + quoted + ' ORDER BY rowid'):
            # These schemas use rowid tables; type tags avoid BLOB/string collisions.
            typed = [('bytes', value.hex()) if isinstance(value, bytes) else (type(value).__name__, value) for value in row]
            digest.update(dumps(typed).encode());digest.update(b'\n');count += 1
        counts[name] = count
    for row in con.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE type IN ('index','trigger') ORDER BY type,name"):
        digest.update(dumps(row).encode())
    return {'schema_version': version, 'logical_sha256': digest.hexdigest(), 'row_counts': counts}


def backup(source, destination, *, timeout_seconds=60):
    source, destination = Path(source).resolve(strict=True), Path(destination).absolute()
    if source == destination or destination.exists():
        raise ValueError('backup/restore destination must be a new path')
    manifest_path = Path(str(destination) + '.manifest.json')
    partial = Path(str(destination) + '.partial')
    if manifest_path.exists():
        raise ValueError('backup manifest already exists')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with closing(readonly(source)) as original:
        estimate = original.execute('PRAGMA page_count').fetchone()[0] * original.execute('PRAGMA page_size').fetchone()[0]
    if disk_usage(destination.parent).free < 2 * estimate + 209715200:
        raise ValueError('insufficient backup space; require twice snapshot size plus 200 MiB')
    fd = os.open(partial, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600);os.close(fd)
    started = time.monotonic()
    try:
        with closing(readonly(source)) as original, closing(sqlite3.connect(partial)) as copied:
            def progress(status, remaining, total):
                if time.monotonic() - started > timeout_seconds:
                    raise TimeoutError('online backup exceeded time budget')
            original.backup(copied, pages=256, progress=progress, sleep=.05)
            copied.commit()
            evidence = fingerprint(copied)
        with partial.open('rb') as handle:
            os.fsync(handle.fileno())
        manifest = {'format': 'predarb-backup/m5-v1', 'created_at': datetime.now(timezone.utc).isoformat(),
                    'file_sha256': file_hash(partial), **evidence}
        # link is atomic and refuses an existing destination; no overwrite race.
        os.link(partial, destination);partial.unlink()
        with manifest_path.open('x') as handle:
            os.chmod(manifest_path, 0o600)
            handle.write(dumps(manifest) + '\n');handle.flush();os.fsync(handle.fileno())
        directory_fd = os.open(destination.parent, os.O_RDONLY)
        try: os.fsync(directory_fd)
        finally: os.close(directory_fd)
        return manifest | {'destination': str(destination), 'manifest': str(manifest_path)}
    finally:
        if partial.exists(): partial.unlink()


def read_manifest(path):
    """Bounded structural validation only; this does not verify snapshot contents."""
    with Path(path).open('rb') as source: raw = source.read(2000001)
    if len(raw) > 2000000: raise ValueError('backup manifest exceeds size limit')
    manifest = object_value(load_json(raw))
    utc_time(text_field(manifest, 'created_at'))
    if text_field(manifest, 'format') != 'predarb-backup/m5-v1':
        raise ValueError('unsupported backup manifest format')
    if not 1 <= field(manifest, 'schema_version', int) <= 8:
        raise ValueError('unsupported backup manifest schema')
    for key in ('file_sha256', 'logical_sha256'):
        if not re.fullmatch('[0-9a-f]{64}', text_field(manifest, key)):
            raise ValueError('invalid backup manifest ' + key)
    counts = field(manifest, 'row_counts', dict)
    if not counts or any(not name or type(count) is not int or count < 0 for name, count in counts.items()):
        raise ValueError('invalid backup manifest row counts')
    return manifest


def verify(path):
    path = Path(path).resolve(strict=True)
    manifest = read_manifest(str(path) + '.manifest.json')
    if file_hash(path) != manifest['file_sha256']:
        raise ValueError('backup file/manifest hash mismatch')
    with closing(readonly(path)) as con:
        actual = fingerprint(con)
    if any(key not in manifest or actual[key] != manifest[key] for key in actual):
        raise ValueError('backup logical fingerprint mismatch')
    return manifest | {'verified': True}


def restore(source, destination):
    before = verify(source)
    result = backup(source, destination)
    if result['logical_sha256'] != before['logical_sha256'] or result['row_counts'] != before['row_counts']:
        raise ValueError('restore fingerprint mismatch; destination is not a verified restore')
    return result | {'restore_verified': True, 'source_file_sha256': before['file_sha256']}
