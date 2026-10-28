"""Bounded private inference for retrieval only. No account or execution imports."""
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from email.utils import parsedate_to_datetime
from http.client import HTTPException
import hashlib
import json
import math
import os
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler

from .store import archive_response, validate_observation
from .validation import load_json, field, text_field, dumps, utc_time

VERSION = 'llama-embeddings/v1'
TEXT_VERSION = 'public-market-text/v1'
PROBE = 'Prediction market public event definition dimension probe.'
SCHEMA = '''
CREATE TABLE IF NOT EXISTS embedding_cache (
 identity TEXT NOT NULL, content_hash TEXT NOT NULL, vector_json TEXT NOT NULL,
 dimensions INTEGER NOT NULL, observation_id INTEGER NOT NULL REFERENCES raw_observations(id),
 created_at TEXT NOT NULL, PRIMARY KEY(identity,content_hash)
);
CREATE TABLE IF NOT EXISTS embedding_breakers (
 endpoint TEXT PRIMARY KEY, retry_at REAL NOT NULL
);
'''


class EmbeddingError(ValueError):
    """Sanitized reason safe to include in discovery reports."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def endpoint(value):
    try:
        parsed = urlsplit(value)
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
                or parsed.query or parsed.fragment or parsed.port not in (None, 443)
                or parsed.path.rstrip('/') not in ('', '/v1', '/v1/embeddings')):
            raise ValueError()
    except ValueError:
        raise EmbeddingError('INVALID_EMBEDDING_URL') from None
    return 'https://' + parsed.netloc + '/v1'


def public_text(contract):
    # Never serialize the instrument, raw metadata, review forms, account state or env.
    allowed = ('question', 'title', 'subtitle', 'yes_sub_title', 'description',
               'rules_primary', 'rules_secondary', 'close_time', 'endDate')
    selected = {key: text_field(contract, key, empty=True) for key in allowed if key in contract and contract[key] is not None}
    text = dumps({'schema': TEXT_VERSION, 'public_contract': selected})
    if len(text.encode()) > 16000:
        raise EmbeddingError('MARKET_TEXT_TOO_LARGE')
    return text


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def vector(value, dimensions=None):
    if not isinstance(value, list) or not 1 <= len(value) <= 8192:
        raise EmbeddingError('INVALID_VECTOR_DIMENSIONS')
    if dimensions is not None and len(value) != dimensions:
        raise EmbeddingError('VECTOR_DIMENSIONS_CHANGED')
    if any(type(x) not in (int, float, Decimal) for x in value):
        raise EmbeddingError('INVALID_VECTOR_NUMBER')
    values = tuple(float(x) for x in value)
    norm = math.hypot(*values)
    if not all(math.isfinite(x) for x in values) or not math.isfinite(norm) or norm == 0:
        raise EmbeddingError('INVALID_VECTOR_NORM')
    return tuple(x / norm for x in values)


@dataclass(frozen=True)
class Config:
    url: str
    timeout: float = 5
    retries: int = 2
    batch_size: int = 16
    cooldown: int = 60
    max_items: int = 512  # legacy synthetic benchmark only; production uses semantic.index_batch
    max_requests: int = 100
    cache_days: int = 30
    cache_rows: int = 20000

    def __post_init__(self):
        endpoint(self.url)
        if any(type(getattr(self, name)) is not int for name in ('retries', 'batch_size', 'cooldown', 'max_items', 'max_requests', 'cache_days', 'cache_rows')):
            raise EmbeddingError('INVALID_EMBEDDING_LIMITS')
        if not (0 < self.timeout <= 30 and 0 <= self.retries <= 3 and 1 <= self.batch_size <= 64
                and 1 <= self.cooldown <= 3600 and 1 <= self.max_items <= 512
                and 1 <= self.max_requests <= 100 and 1 <= self.cache_days <= 365
                and 1 <= self.cache_rows <= 20000):
            raise EmbeddingError('INVALID_EMBEDDING_LIMITS')


class Client:
    def __init__(self, con, config, *, opener=None, clock=time.time, sleep=time.sleep):
        self.con, self.config = con, config
        self.base = endpoint(config.url)
        self.open = opener or build_opener(ProxyHandler({}), NoRedirect()).open
        self.clock, self.sleep = clock, sleep
        self.requests = 0
        self.model = self.identity = None
        self.dimensions = None
        self.hits = 0

    def _trip(self, delay=0):
        self.con.execute('INSERT OR REPLACE INTO embedding_breakers VALUES(?,?)',
                         (self.base, self.clock() + max(self.config.cooldown, delay)))
        self.con.commit()

    def _request(self, route, payload=None):
        state = self.con.execute('SELECT retry_at FROM embedding_breakers WHERE endpoint=?', (self.base,)).fetchone()
        if state and state[0] > self.clock():
            raise EmbeddingError('CIRCUIT_OPEN')
        for attempt in range(self.config.retries + 1):
            if self.requests >= self.config.max_requests:
                raise EmbeddingError('REQUEST_BUDGET_EXHAUSTED')
            self.requests += 1
            delay = 2 ** attempt
            request = Request(self.base + route, data=dumps(payload).encode() if payload is not None else None,
                              headers={'Content-Type': 'application/json', 'Accept': 'application/json'})
            try:
                try:
                    response = self.open(request, timeout=self.config.timeout)
                except HTTPError as exc:
                    response = exc
                with response:
                    status, headers = response.status, dict(response.headers)
                    body = response.read(4 * 1024 * 1024 + 1)
                truncated = len(body) > 4 * 1024 * 1024
                raw = archive_response(self.con, 'embedding', request.full_url, body[:4 * 1024 * 1024],
                                       status, headers, datetime.fromtimestamp(self.clock(), timezone.utc).isoformat(),
                                       VERSION, truncated=truncated)
                if status == 200 and not truncated:
                    try:
                        return load_json(body), raw
                    except ValueError:
                        validate_observation(self.con, raw, 'REJECTED', 'INVALID_JSON')
                        raise EmbeddingError('INVALID_JSON') from None
                validate_observation(self.con, raw, 'REJECTED', 'HTTP_OR_SIZE_ERROR')
                retryable = status in (408, 429, 500, 502, 503, 504) and not truncated
                reason = 'HTTP_OR_SIZE_ERROR'
                # Never retry sooner than Retry-After; long/unknown delays open the circuit.
                delay = 2 ** attempt
                retry_after = next((v for k, v in headers.items() if k.lower() == 'retry-after'), None)
                if retry_after is not None:
                    try:
                        delay = max(delay, int(retry_after))
                    except (ValueError, TypeError):
                        try:
                            delay = max(delay, parsedate_to_datetime(retry_after).timestamp() - self.clock())
                        except (ValueError, TypeError, OverflowError):
                            retryable = False
                    if delay > 8:
                        retryable = False
            except (OSError, URLError, HTTPException):
                retryable, reason, delay = True, 'SERVICE_UNREACHABLE', 2 ** attempt
            except EmbeddingError:
                self._trip()
                raise
            if not retryable or attempt == self.config.retries:
                self._trip(delay)
                raise EmbeddingError(reason)
            self.sleep(delay)
        raise AssertionError('unreachable')

    def _decode(self, payload, raw, count, dimensions=None):
        try:
            if text_field(payload, 'object') != 'list' or text_field(payload, 'model') != self.model:
                raise EmbeddingError('MODEL_OR_SCHEMA_CHANGED')
            data = field(payload, 'data', list)
            if len(data) != count:
                raise EmbeddingError('BATCH_COUNT_MISMATCH')
            ordered = {}
            for item in data:
                index = field(item, 'index', int)
                if not 0 <= index < count or index in ordered or text_field(item, 'object') != 'embedding':
                    raise EmbeddingError('INVALID_BATCH_INDEX')
                values = vector(field(item, 'embedding', list), dimensions)
                dimensions = len(values)
                ordered[index] = values
            validate_observation(self.con, raw, 'VALID', None)
            return [ordered[i] for i in range(count)]
        except (ValueError, TypeError, OverflowError):
            validate_observation(self.con, raw, 'REJECTED', 'INVALID_EMBEDDING_SCHEMA')
            self._trip()
            raise EmbeddingError('INVALID_EMBEDDING_SCHEMA') from None

    def probe(self):
        payload, raw = self._request('/models')
        try:
            if text_field(payload, 'object') != 'list':
                raise ValueError()
            models = field(payload, 'data', list)
            if len(models) != 1:
                raise ValueError()
            self.model = text_field(models[0], 'id')
            if len(self.model) > 512:
                raise ValueError()
        except (ValueError, TypeError):
            validate_observation(self.con, raw, 'REJECTED', 'AMBIGUOUS_MODEL_SCHEMA')
            self._trip()
            raise EmbeddingError('AMBIGUOUS_MODEL_SCHEMA') from None
        validate_observation(self.con, raw, 'VALID', None)
        payload, raw = self._request('/embeddings', {'model': self.model, 'input': [PROBE], 'encoding_format': 'float'})
        probe = self._decode(payload, raw, 1)[0]
        self.dimensions = len(probe)
        # Probe fingerprint also isolates same-name model replacements. Tiny numerical
        # changes can conservatively miss cache; they never mix vector spaces.
        self.identity = digest(dumps([self.base, self.model, VERSION, TEXT_VERSION, probe]))
        self.con.execute('DELETE FROM embedding_breakers WHERE endpoint=?', (self.base,))
        self.con.commit()
        return {'model': self.model, 'identity': self.identity, 'dimensions': self.dimensions}

    def embed(self, texts):
        if self.identity is None:
            self.probe()
        unique = {digest(text): text for text in texts}
        result, missing = {}, []
        now = datetime.fromtimestamp(self.clock(), timezone.utc)
        for key, text in unique.items():
            row = self.con.execute('SELECT vector_json,dimensions,created_at FROM embedding_cache WHERE identity=? AND content_hash=?',
                                   (self.identity, key)).fetchone()
            if row and 0 <= (now - utc_time(row[2])).total_seconds() <= self.config.cache_days * 86400:
                try:
                    if row[1] != self.dimensions:
                        raise ValueError()
                    result[key] = vector(load_json(row[0]), self.dimensions)
                    self.hits += 1
                    continue
                except (ValueError, TypeError, OverflowError):
                    pass  # corrupt cache is derived data: replace from inference
            missing.append(key)
        for start in range(0, len(missing), self.config.batch_size):
            keys = missing[start:start + self.config.batch_size]
            payload, raw = self._request('/embeddings', {'model': self.model, 'input': [unique[k] for k in keys], 'encoding_format': 'float'})
            vectors = self._decode(payload, raw, len(keys), self.dimensions)
            for key, values in zip(keys, vectors):
                result[key] = values
                self.con.execute('INSERT OR REPLACE INTO embedding_cache VALUES(?,?,?,?,?,?)',
                                 (self.identity, key, dumps(values), self.dimensions, raw, now.isoformat()))
            self.con.commit()
        self.con.execute('DELETE FROM embedding_cache WHERE rowid IN (SELECT rowid FROM embedding_cache ORDER BY created_at DESC, rowid DESC LIMIT -1 OFFSET ?)', (self.config.cache_rows,))
        self.con.commit()
        return [result[digest(text)] for text in texts]


def from_environment(con):
    value = os.environ.get('PREDARB_EMBEDDING_URL')
    return Client(con, Config(value)) if value else None


def retrieve(con, pools, client, *, top_k=5, minimum=0.75):
    """Legacy synthetic benchmark helper; production uses the persistent semantic index."""
    selected = [[row for row in pool if row['features']['sports'] is None][:client.config.max_items] for pool in pools]
    report = {'status': 'READY', 'eligible': [len(p) for p in pools], 'selected': [len(p) for p in selected], 'embedded': [0, 0],
              'non_sports_eligible': [sum(r['features']['sports'] is None for r in p) for p in pools],
              'excluded_sports': [sum(r['features']['sports'] is not None for r in p) for p in pools],
              'truncated': any(sum(r['features']['sports'] is None for r in pool) > len(sel) for pool, sel in zip(pools, selected))}
    if not all(selected):
        return {}, dict(report, status='EMPTY', reason='NO_NON_SPORTS_MARKETS_ON_BOTH_VENUES')
    rows = selected[0] + selected[1]
    texts = [public_text(load_json(con.execute('SELECT evidence_json FROM rule_versions WHERE id=?', (row['version_id'],)).fetchone()[0])['contract']) for row in rows]
    values = client.embed(texts)
    report.update(embedded=[len(p) for p in selected], model=client.model, identity=client.identity, dimensions=client.dimensions,
                  requests=client.requests, cache_hits=client.hits)
    pairs = {}
    for k, kv in zip(selected[0], values[:len(selected[0])]):
        ranked = []
        for p, pv in zip(selected[1], values[len(selected[0]):]):
            if k['hypothetical'] != p['hypothetical']:
                continue
            score = max(-1.0, min(1.0, sum(a*b for a,b in zip(kv,pv))))
            if score >= minimum:
                ranked.append((-score, p['source_id'], p))
        for neg, _, p in sorted(ranked, key=lambda item: item[:2])[:top_k]:
            pairs[(k['source_id'], p['source_id'])] = {'cosine': -neg, 'model': client.model,
                'identity': client.identity, 'dimensions': client.dimensions, 'versions': [k['version_id'], p['version_id']]}
    return pairs, report
