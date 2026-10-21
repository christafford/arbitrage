"""Read-only catalogue traversal and selected detail/book evidence capture."""
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
from .provider import HttpClient
from .store import (save_book, save_entry, start_run, update_run, validate_observation)
from .validation import SchemaError, dumps, identifier, utc_time


@dataclass(frozen=True)
class CollectionResult:
    run_id: int
    venue: str
    status: str
    pages: int
    records: int
    unique_records: int
    duplicates: int
    next_page: str | None
    books: int

    def as_dict(self):
        return asdict(self)


def book_freshness(source_ts, received_at, *, now=None, max_age=60):
    if max_age <= 0:
        raise ValueError('max_age must be positive')
    now = now or datetime.now(timezone.utc)
    received = utc_time(received_at)
    if (now - received).total_seconds() > max_age:
        return 'STALE_RECEIPT'
    if (now - received).total_seconds() < -5:
        return 'FUTURE_RECEIPT'
    if source_ts is None:
        return 'UNKNOWN_SOURCE_TIME'
    age = (now - utc_time(source_ts)).total_seconds()
    if age < -5:
        return 'FUTURE_SOURCE_TIME'
    return 'STALE_SOURCE' if age > max_age else 'FRESH'


def collect(con, adapter, *, page_size=20, max_pages=10, scope=None, books=1,
            selected=(), max_age=60, client=None, now=None):
    if not 1 <= page_size <= 1000 or not 1 <= max_pages <= 10000:
        raise ValueError('page_size must be 1..1000 and max_pages 1..10000')
    if not 0 <= books <= 100 or type(max_age) is not int or not 1 <= max_age <= 3600 or len(selected) > 100:
        raise ValueError('books must be 0..100, at most 100 selections, and max_age 1..3600')
    if scope:
        identifier(scope)
    selected = tuple(dict.fromkeys(identifier(value) for value in selected))
    run_id = start_run(con, adapter.VENUE, adapter.SCHEMA_VERSION,
                       {'filter': scope, 'page_size': page_size, 'max_pages': max_pages,
                        'books': books, 'selected': selected, 'max_age_seconds': max_age})
    pages = records = captured = 0
    continuation = None
    seen, page_hashes, cursors = {}, set(), set()
    client = client or HttpClient(con, adapter.VENUE)
    events, series = {}, {}
    try:
        for _ in range(max_pages):
            def validate_page(data):
                adapter.validate_page(data)
                if len(data['markets']) > page_size:
                    raise SchemaError('provider exceeded requested page size')
                for item in data['markets']:
                    if scope and (item['event_ticker'] if adapter.VENUE == 'kalshi'
                                  else item[adapter.ID_FIELD]) != scope:
                        raise SchemaError('provider returned market outside requested scope')
            observation = client.get(adapter.page_url(page_size, continuation, scope),
                                     adapter.SCHEMA_VERSION, validate_page)
            data = observation.data
            markets = data['markets']
            fingerprint = hashlib.sha256(dumps(markets).encode()).hexdigest()
            if markets and fingerprint in page_hashes:
                raise SchemaError('pagination repeated a page; archive is incomplete')
            page_hashes.add(fingerprint)
            previous_count = len(seen)
            for market in markets:
                source_id = market[adapter.ID_FIELD]
                seen[source_id] = market
                save_entry(con, run_id, observation, source_id, market, adapter.rules(market),
                           market[adapter.TIME_FIELD])
            pages += 1
            records += len(markets)
            following = adapter.next_page(data, continuation, page_size)
            if following is not None and (following in cursors or (markets and len(seen) == previous_count)
                                          or not markets):
                raise SchemaError('pagination cursor/offset did not advance')
            if following is not None:
                cursors.add(following)
            continuation = following
            update_run(con, run_id, status='RUNNING', pages=pages, records=records,
                       unique=len(seen), next_page=continuation)
            if continuation is None:
                break

        chosen = selected or tuple(seen)[:books]
        for source_id in chosen:
            if source_id not in seen:
                raise ValueError(f'selected source {source_id} was not in the captured catalogue scope')

            def validate_detail(data):
                adapter.validate_detail(data)
                if data['market'][adapter.ID_FIELD] != source_id:
                    raise SchemaError('detail identity mismatch')
                if adapter.VENUE == 'kalshi':
                    if data['market']['event_ticker'] != seen[source_id]['event_ticker']:
                        raise SchemaError('detail event identity mismatch')
                elif data['market']['id'] != seen[source_id]['id']:
                    raise SchemaError('detail market id mismatch')
            detail = client.get(adapter.detail_url(source_id), adapter.SCHEMA_VERSION, validate_detail)
            market = detail.data['market']
            rules = adapter.rules(market)
            if adapter.VENUE == 'kalshi':
                event_id = market['event_ticker']
                if event_id not in events:
                    def validate_event(data):
                        adapter.validate_event(data)
                        if data['event']['event_ticker'] != event_id:
                            raise SchemaError('event identity mismatch')
                    events[event_id] = client.get(adapter.event_url(market), adapter.SCHEMA_VERSION,
                                                 validate_event)
                event = events[event_id]
                rules['event_evidence'] = event.data['event']
                rules['event_endpoint'] = event.endpoint
                series_id = event.data['event']['series_ticker']
                if series_id not in series:
                    def validate_series(data):
                        adapter.validate_series(data)
                        if data['series']['ticker'] != series_id:
                            raise SchemaError('series identity mismatch')
                    series[series_id] = client.get(adapter.series_url(series_id), adapter.SCHEMA_VERSION,
                                                   validate_series)
                rules['series_evidence'] = series[series_id].data['series']
                rules['series_endpoint'] = series[series_id].endpoint
            save_entry(con, run_id, detail, source_id, market, rules, market[adapter.TIME_FIELD])
            validate_observation(con, detail.id, 'VALID', None, market[adapter.TIME_FIELD])

            def validate_book(data):
                adapter.validate_book(data)
                if adapter.VENUE == 'polymarket_us' and data['marketData']['marketSlug'] != source_id:
                    raise SchemaError('book identity mismatch')
            book = client.get(adapter.book_url(source_id), adapter.SCHEMA_VERSION, validate_book)
            source_ts, sizes = adapter.book_info(book.data)
            freshness = book_freshness(source_ts, book.received_at, max_age=max_age, now=now)
            liquidity = ('EMPTY' if not any(sizes) else 'PARTIAL' if not all(sizes) else 'TWO_SIDED')
            save_book(con, run_id, book, source_id, source_ts, freshness, liquidity)
            from .book_store import record_normalization
            record_normalization(con, book.id, detail.id, now=now, max_age=max_age)
            captured += 1
        status = 'COMPLETE' if continuation is None else 'PARTIAL'
        update_run(con, run_id, status=status, pages=pages, records=records,
                   unique=len(seen), next_page=continuation)
        return CollectionResult(run_id, adapter.VENUE, status, pages, records, len(seen),
                                records - len(seen), continuation, captured)
    except BaseException as exc:
        update_run(con, run_id, status='INTERRUPTED' if isinstance(exc, KeyboardInterrupt) else 'FAILED',
                   pages=pages, records=records, unique=len(seen), next_page=continuation,
                   error=str(exc) or type(exc).__name__)
        raise
