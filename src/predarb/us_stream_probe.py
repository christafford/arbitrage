"""Bounded US market-data diagnostics, isolated from economic eligibility."""
import base64
from collections import Counter
from datetime import datetime, timezone
import hashlib
import logging
from pathlib import Path
import re
import shutil
import statistics
import time
from uuid import UUID

from .kalshi_auth import private_file
from . import polymarket_us as us
from .validation import amount, dumps, load_json, identifier, utc_time

URL = 'wss://api.polymarket.us/v1/ws/markets'
PATH = '/v1/ws/markets'
SCHEMA = 'polymarket-us-markets-ws/m5n-probe-v2'
MAX_FRAMES = 5000
MAX_BYTES = 16 * 1024**2
MIN_FREE_BYTES = 1024**3


class Credentials:
    """No general-purpose signing method; only the fixed market-data handshake."""
    def __init__(self, key_id, key, secret):
        self._id, self._key, self._secret = key_id, key, secret

    @classmethod
    def load(cls, path):
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        except ImportError:
            raise ValueError('install the market-data-ws optional dependencies') from None
        try:
            fields = {}
            for line in private_file(path).decode().splitlines():
                if not line.strip(): continue
                name, value = line.split('=', 1)
                if name in fields: raise ValueError()
                fields[name] = value.strip()
            # Explicit legacy spelling supplied by this operator; no shell evaluation.
            aliases = ('POLYMARKET_API_SECRET_KEY', 'POLYMARKET_API_SECDRET_KEY')
            names = [name for name in aliases if name in fields]
            if len(names) != 1 or set(fields) != {'POLYMARKET_API_KEY_ID', names[0]}:
                raise ValueError()
            key_id = str(UUID(fields['POLYMARKET_API_KEY_ID']))
            secret = fields[names[0]]
            raw = base64.b64decode(secret, validate=True)
            if len(raw) not in (32, 64): raise ValueError()
            key = Ed25519PrivateKey.from_private_bytes(raw[:32])
            if len(raw) == 64 and raw[32:] != key.public_key().public_bytes_raw():
                raise ValueError()
            return cls(key_id, key, secret)
        except (ValueError, TypeError, UnicodeError):
            raise ValueError('invalid US credential file or key format') from None

    def headers(self, timestamp_ms=None):
        stamp = str(time.time_ns() // 1_000_000 if timestamp_ms is None else timestamp_ms)
        signature = base64.b64encode(self._key.sign((stamp + 'GET' + PATH).encode())).decode()
        return {'X-PM-Access-Key': self._id, 'X-PM-Timestamp': stamp,
                'X-PM-Signature': signature}

    def sensitive_values(self, headers):
        return (self._id, self._secret, headers['X-PM-Signature'])


def open_socket(headers):
    from websockets.sync.client import reconnect
    class FixedOrigin(reconnect):
        def process_redirect(self, exc): return exc
    logger = logging.Logger('predarb.private_us_market_probe'); logger.disabled = True
    return FixedOrigin(URL, additional_headers=headers, proxy=None, compression=None,
                       open_timeout=10, close_timeout=2, ping_interval=10, ping_timeout=10,
                       max_size=1_000_000, max_queue=16, logger=logger).connect()


def subscription(slugs):
    if not isinstance(slugs, (list, tuple)) or any(not isinstance(s, str) for s in slugs):
        raise ValueError('market slugs must be a list of strings')
    if not 1 <= len(slugs) <= 2 or len(set(slugs)) != len(slugs):
        raise ValueError('probe requires one or two distinct market slugs')
    for slug in slugs: identifier(slug)
    return {'subscribe': {'requestId': 'm5n-market-data',
                          'subscriptionType': 'SUBSCRIPTION_TYPE_MARKET_DATA',
                          'marketSlugs': list(slugs)}}


def safe_frame(body, secrets=()):
    """Privacy screening before archival; semantic validation after archival.

    Unknown, error, malformed or enriched frames retain only a digest and marker.
    Known public shapes retain exact wire bytes, including invalid numeric fields.
    """
    raw = body.encode() if isinstance(body, str) else body
    digest = hashlib.sha256(raw).hexdigest()
    marker = b'{"redacted":"UNSAFE_OR_UNKNOWN_FRAME"}'
    try:
        if len(raw) > 1_000_000 or any(s.encode() in raw for s in secrets if s):
            return marker, digest, False
        f = load_json(raw)
        if any(s in dumps(f) for s in secrets if s): return marker, digest, False
        if not isinstance(f, dict): return marker, digest, False
        if set(f) == {'heartbeat'} and f['heartbeat'] == {}: return raw, digest, True
        if not set(f) <= {'requestId', 'subscriptionType', 'marketData'} or 'marketData' not in f:
            return marker, digest, False
        b = f['marketData']
        if not isinstance(b, dict) or not set(b) <= {'marketSlug','bids','offers','state','stats','transactTime'}:
            return marker, digest, False
        strings = [f.get('requestId'), f.get('subscriptionType'), b.get('marketSlug'), b.get('state'), b.get('transactTime')]
        if any(x is not None and (not isinstance(x,str) or not re.fullmatch(r'[A-Za-z0-9_.:+\-]{1,250}',x)) for x in strings):
            return marker, digest, False
        def amount(x):
            return isinstance(x,dict) and set(x) <= {'value','currency'} and all(
                isinstance(v,str) and re.fullmatch(r'[A-Za-z0-9.+\-]{1,40}',v) for v in x.values())
        for side in ('bids','offers'):
            if side not in b: continue  # Missing fields must reach semantic rejection.
            if not isinstance(b[side],list): return marker,digest,False
            for level in b[side]:
                if not isinstance(level,dict) or not set(level) <= {'px','qty'}: return marker,digest,False
                if 'px' in level and not amount(level['px']): return marker,digest,False
                if 'qty' in level and (not isinstance(level['qty'],str) or not re.fullmatch(r'[0-9.+\-]{1,40}',level['qty'])): return marker,digest,False
        if 'stats' in b:
            stats=b['stats']
            prices={'openPx','closePx','lowPx','highPx','lastTradePx','indicativeOpenPx',
                    'settlementPx','notionalTraded','tradingReferencePx','currentPx'}
            times={'openSetTime','closeSetTime','highSetTime','lowSetTime','lastTradeSetTime',
                   'indicativeOpenSetTime','settlementSetTime','openInterestSetTime',
                   'notionalSetTime','tradingReferenceSetTime'}
            quantities={'sharesTraded','lastTradeQty','openInterest'}
            if not isinstance(stats,dict) or not set(stats) <= prices|times|quantities|{'lastPriceSample','settlementPreliminaryFlag','settlementPriceCalculationMethod'}:
                return marker,digest,False
            for key,value in stats.items():
                if key in prices:
                    if not amount(value): return marker,digest,False
                elif key=='lastPriceSample':
                    if not isinstance(value,dict) or not set(value)<={'longPx','shortPx','ts'}: return marker,digest,False
                    for k,v in value.items():
                        if k=='ts':
                            if not isinstance(v,str) or not re.fullmatch(r'[0-9TtZz.:+\-]{1,50}',v): return marker,digest,False
                        elif not amount(v): return marker,digest,False
                elif key=='settlementPreliminaryFlag':
                    if type(value) is not bool: return marker,digest,False
                elif key in times:
                    if not isinstance(value,str) or not re.fullmatch(r'[0-9TtZz.:+\-]{1,50}',value): return marker,digest,False
                elif key=='settlementPriceCalculationMethod':
                    if not isinstance(value,str) or not re.fullmatch(r'[A-Z0-9_]{1,100}',value): return marker,digest,False
                elif not isinstance(value,str) or not re.fullmatch(r'[0-9.+\-]{1,40}',value): return marker,digest,False
        return raw,digest,True
    except (ValueError,TypeError,AttributeError,RecursionError):
        return marker,digest,False


def assess(raw, slugs, received_at, previous=None):
    f=load_json(raw)
    if not isinstance(f, dict): raise ValueError('expected frame object')
    if set(f)=={'heartbeat'} and f['heartbeat']=={}: return {'kind':'heartbeat'}
    if f.get('requestId')!='m5n-market-data' or f.get('subscriptionType')!='SUBSCRIPTION_TYPE_MARKET_DATA':
        raise ValueError('unexpected subscription envelope')
    us.validate_book(f); b=f['marketData']
    if b['marketSlug'] not in slugs: raise ValueError('wrong market identity')
    age=(utc_time(received_at)-utc_time(b['transactTime'])).total_seconds()
    reasons=[]
    if age < 0: reasons.append('FUTURE_SOURCE')
    if age > 2: reasons.append('SOURCE_AGE_GT_2S')
    if b['state']!='MARKET_STATE_OPEN': reasons.append('MARKET_NOT_OPEN')
    if not b['bids'] or not b['offers']: reasons.append('PARTIAL_OR_EMPTY_BOOK')
    bids = [amount(level['px']) for level in b['bids']]
    offers = [amount(level['px']) for level in b['offers']]
    if bids != sorted(bids, reverse=True) or offers != sorted(offers):
        reasons.append('UNSORTED_BOOK')
    if bids and offers and max(bids) >= min(offers):
        reasons.append('CROSSED_OR_LOCKED_BOOK')
    if previous and utc_time(b['transactTime']) < utc_time(previous['source_ts']): reasons.append('SOURCE_REGRESSION')
    digest=hashlib.sha256(dumps([b['bids'],b['offers']]).encode()).hexdigest()
    return {'kind':'book','market':b['marketSlug'],'source_ts':b['transactTime'],
            'source_age_seconds':age,'depth_sha256':digest,
            'changed_from_previous':None if previous is None else digest!=previous['depth_sha256'],
            'bid_levels':len(b['bids']),'offer_levels':len(b['offers']),
            'rejections':reasons,'timestamp_depth_diagnostic_pass':not reasons,
            'sequence_continuity':'UNKNOWN','economic_eligibility':False}


def summarize(rows, slugs, finished_at):
    """Receipt-time diagnostics only; quiet intervals never inherit freshness."""
    markets = {}
    for slug in slugs:
        books = [row for row in rows if row.get('kind') == 'book' and row['market'] == slug]
        ages = [float(row['source_age_seconds']) for row in books]
        gaps = [float(b['receive_monotonic']) - float(a['receive_monotonic'])
                for a, b in zip(books, books[1:])]
        markets[slug] = {
            'books': len(books),
            'timestamp_depth_passes': sum(row['timestamp_depth_diagnostic_pass'] for row in books),
            'rejections': dict(Counter(reason for row in books for reason in row['rejections'])),
            'depth_changes': sum(row['changed_from_previous'] is True for row in books),
            'unchanged_depth': sum(row['changed_from_previous'] is False for row in books),
            'source_age_seconds': {'min': min(ages), 'median': statistics.median(ages), 'max': max(ages)} if ages else None,
            'max_interarrival_seconds': max(gaps) if gaps else None,
            'last_receive_at': books[-1]['received_at'] if books else None,
            'last_source_age_at_finish_seconds': (
                utc_time(finished_at) - utc_time(books[-1]['source_ts'])).total_seconds() if books else None,
            'sequence_continuity': 'UNKNOWN', 'economic_eligibility': False,
        }
    return {'markets': markets, 'missing_markets': [slug for slug in slugs if not markets[slug]['books']]}


def capture(directory, credentials, slugs, *, seconds=30, connect_socket=open_socket, stop=None):
    """One generation, fixed monotonic deadline; no automatic retry or approval."""
    if type(seconds) is not int or not 1 <= seconds <= 600: raise ValueError('duration must be 1..600 seconds')
    request=subscription(slugs); directory=Path(directory); directory.mkdir(parents=True,exist_ok=False)
    started=datetime.now(timezone.utc); start=time.monotonic();deadline=start+seconds
    stats={'schema':SCHEMA,'started_at':started.isoformat(),'requested_seconds':seconds,
           'slugs':list(slugs),'endpoint':URL,'frames':0,'books':0,'heartbeats':0,
           'reason':'NOT_CONNECTED','continuity':'UNKNOWN','economic_eligibility':False,
           'start_monotonic':start,'connection_generation':1,'last_pong_rtt_seconds':None}
    previous={};total_bytes=0;rows=[]
    (directory/'timing.jsonl').touch()
    def emit(row):
        with (directory/'timing.jsonl').open('a') as handle: handle.write(dumps(row)+'\n')
        rows.append(row)
    try:
        if shutil.disk_usage(directory).free < MIN_FREE_BYTES:
            raise ValueError('low disk')
        headers=credentials.headers();secrets=credentials.sensitive_values(headers)
        with connect_socket(headers) as socket:
            stats['handshake_seconds']=time.monotonic()-start
            if time.monotonic() >= deadline:
                stats['reason']='DEADLINE_DURING_HANDSHAKE'
            else:
                socket.send(dumps(request));stats['reason']='BUDGET_COMPLETE'
            while time.monotonic()<deadline and stats['frames']<MAX_FRAMES:
                if stop is not None and stop.is_set(): stats['reason']='INTERRUPTED';break
                if shutil.disk_usage(directory).free < MIN_FREE_BYTES: stats['reason']='LOW_DISK';break
                # Reserve one maximum-sized frame before receiving it.
                if total_bytes+1_000_000>MAX_BYTES: stats['reason']='BYTE_LIMIT';break
                mono=time.monotonic();wall=datetime.now(timezone.utc)
                if abs((wall-started).total_seconds()-(mono-start))>1:
                    stats['reason']='WALL_CLOCK_JUMP';break
                latency=getattr(socket,'latency',0)
                if latency > 0: stats['last_pong_rtt_seconds']=latency
                try: body=socket.recv(timeout=min(.5,max(.001,deadline-time.monotonic())))
                except TimeoutError: continue
                mono=time.monotonic();wall=datetime.now(timezone.utc).isoformat()
                stats['frames']+=1
                safe,digest,public=safe_frame(body,secrets)
                filename=f"{stats['frames']:06d}.json";(directory/filename).write_bytes(safe)
                total_bytes+=len(safe)
                row={'frame':stats['frames'],'raw_file':filename,'wire_sha256':digest,
                     'archive_sha256':hashlib.sha256(safe).hexdigest(),'public_shape':public,
                     'received_at':wall,'receive_monotonic':mono,'connection_generation':1}
                if not public:
                    row['rejection']='UNSAFE_OR_UNKNOWN_FRAME';emit(row);stats['reason']=row['rejection'];break
                if abs((utc_time(wall)-started).total_seconds()-(mono-start))>1:
                    row['rejection']='WALL_CLOCK_JUMP';emit(row);stats['reason']=row['rejection'];break
                try:
                    market=load_json(safe).get('marketData',{}).get('marketSlug')
                    result=assess(safe,slugs,wall,previous.get(market));row.update(result)
                    if result['kind']=='book':
                        stats['books']+=1;previous[market]=result
                    else: stats['heartbeats']+=1
                except (ValueError,TypeError,KeyError):
                    row['rejection']='INVALID_FRAME';emit(row);stats['reason']=row['rejection'];break
                emit(row)
            if stats['frames']>=MAX_FRAMES: stats['reason']='FRAME_LIMIT'
    except KeyboardInterrupt: stats['reason']='INTERRUPTED'
    except Exception as exc:
        # Never log exception repr, response body or handshake headers.
        stats['reason']='LOW_DISK' if isinstance(exc,ValueError) and str(exc)=='low disk' else 'CAPTURE_ERROR'
        stats['error_type']=type(exc).__name__
        response=getattr(exc,'response',None)
        if response is not None: stats['http_status']=getattr(response,'status_code',None)
    stats['finished_at']=datetime.now(timezone.utc).isoformat();stats['elapsed_seconds']=time.monotonic()-start
    stats['archived_frame_bytes']=total_bytes
    stats.update(summarize(rows,slugs,stats['finished_at']))
    stats['capture_complete']=(stats['reason']=='BUDGET_COMPLETE' and not stats['missing_markets'])
    (directory/'results.json').write_text(dumps(stats)+'\n')
    return stats


def replay(directory):
    """Verify an isolated v2 archive and recompute assessments without a network."""
    directory = Path(directory)
    result = load_json((directory/'results.json').read_bytes())
    if result.get('schema') != SCHEMA or result.get('endpoint') != URL:
        raise ValueError('unsupported capture schema or endpoint')
    slugs = result['slugs']; subscription(slugs)
    rows = [load_json(line) for line in (directory/'timing.jsonl').read_bytes().splitlines()]
    if len(rows) != result['frames'] or len(rows) > MAX_FRAMES:
        raise ValueError('frame count mismatch')
    previous = {}; checked = 0
    for index, row in enumerate(rows, 1):
        filename = f'{index:06d}.json'
        if row['raw_file'] != filename or row['frame'] != index or row['connection_generation'] != 1:
            raise ValueError('invalid frame provenance')
        raw = (directory/filename).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != row['archive_sha256']:
            raise ValueError('archive hash mismatch')
        if not row['public_shape']:
            if raw != b'{"redacted":"UNSAFE_OR_UNKNOWN_FRAME"}' or row.get('rejection') != 'UNSAFE_OR_UNKNOWN_FRAME':
                raise ValueError('invalid redaction record')
            continue
        if digest != row['wire_sha256'] or not safe_frame(raw)[2]:
            raise ValueError('wire hash or public shape mismatch')
        if row.get('rejection') == 'WALL_CLOCK_JUMP': continue
        market = load_json(raw).get('marketData',{}).get('marketSlug')
        try:
            assessment = assess(raw, slugs, row['received_at'], previous.get(market))
        except (ValueError, TypeError, KeyError):
            if row.get('rejection') != 'INVALID_FRAME': raise ValueError('unrecorded invalid frame') from None
            continue
        if 'rejection' in row or load_json(dumps(assessment)) != {key: row.get(key) for key in assessment}:
            raise ValueError('assessment mismatch')
        checked += 1
        if assessment['kind'] == 'book': previous[market] = assessment
    summary = summarize(rows, slugs, result['finished_at'])
    if load_json(dumps(summary)) != {key: result.get(key) for key in summary}:
        raise ValueError('summary mismatch')
    for kind, key in (('book','books'), ('heartbeat','heartbeats')):
        if sum(row.get('kind') == kind for row in rows) != result.get(key):
            raise ValueError('assessment count mismatch')
    complete = result['reason'] == 'BUDGET_COMPLETE' and not summary['missing_markets']
    if result.get('capture_complete') is not complete:
        raise ValueError('capture completion mismatch')
    if result['reason'] == 'BUDGET_COMPLETE' and result['elapsed_seconds'] < result['requested_seconds']:
        raise ValueError('capture duration mismatch')
    return {'schema':SCHEMA,'verified_frames':len(rows),'replayed_assessments':checked,
            'capture_complete':complete,'economic_eligibility':False,**summary}
