"""Kalshi public Trade API 3.34.0; capture bids, never infer executable asks in M1."""
from urllib.parse import urlencode
from .validation import (SchemaError, decimal_value, field, identifier,
                         text_field, utc_time)

BASE = 'https://external-api.kalshi.com/trade-api/v2'
SCHEMA_VERSION = 'kalshi-3.34.0/m1-v1'
VENUE = 'kalshi'
ID_FIELD = 'ticker'
TIME_FIELD = 'updated_time'


def page_url(page_size, continuation, scope):
    params = {'status': 'open', 'mve_filter': 'exclude', 'limit': page_size}
    if continuation:
        params['cursor'] = continuation
    if scope:
        params['event_ticker'] = identifier(scope)
    return BASE + '/markets?' + urlencode(params)


def validate_market(market):
    for key in ('ticker', 'event_ticker'):
        identifier(text_field(market, key))
    if text_field(market, 'market_type') not in {'binary', 'scalar'}:
        raise SchemaError('unknown market_type')
    if text_field(market, 'status') not in {
            'initialized', 'inactive', 'active', 'closed', 'determined', 'disputed', 'amended', 'finalized'}:
        raise SchemaError('unknown market status')
    for key in ('rules_primary', 'rules_secondary', 'yes_sub_title', 'no_sub_title'):
        text_field(market, key, empty=True)
    for key in ('created_time', 'updated_time', 'open_time', 'close_time', 'latest_expiration_time'):
        utc_time(text_field(market, key))
    for key in ('yes_bid_dollars', 'yes_ask_dollars', 'no_bid_dollars', 'no_ask_dollars',
                'last_price_dollars', 'notional_value_dollars'):
        decimal_value(text_field(market, key), price=True)
    for key in ('yes_bid_size_fp', 'yes_ask_size_fp', 'volume_fp', 'volume_24h_fp', 'open_interest_fp'):
        decimal_value(text_field(market, key))
    field(market, 'settlement_timer_seconds', int)
    if market['settlement_timer_seconds'] < 0:
        raise SchemaError('negative settlement timer')


def validate_page(data):
    markets = field(data, 'markets', list)
    field(data, 'cursor', str)
    for market in markets:
        validate_market(market)


def next_page(data, current, page_size):
    return data['cursor'] or None


def detail_url(source_id):
    return BASE + '/markets/' + identifier(source_id)


def validate_detail(data):
    validate_market(field(data, 'market', dict))


def event_url(market):
    return BASE + '/events/' + identifier(market['event_ticker'])


def validate_event(data):
    event = field(data, 'event', dict)
    for key in ('event_ticker', 'series_ticker', 'title'):
        text_field(event, key)
    for source in field(event, 'settlement_sources', list):
        text_field(source, 'name')
        url = text_field(source, 'url')
        if not url.startswith('https://'):
            raise SchemaError('invalid settlement source URL')


def series_url(series_id):
    return BASE + '/series/' + identifier(series_id)


def validate_series(data):
    series = field(data, 'series', dict)
    identifier(text_field(series, 'ticker'))
    text_field(series, 'title')
    for key in ('contract_url', 'contract_terms_url'):
        if not text_field(series, key).startswith('https://'):
            raise SchemaError('invalid official contract URL')
    for prohibition in field(series, 'additional_prohibitions', list):
        if not isinstance(prohibition, str):
            raise SchemaError('invalid additional prohibition')


def rules(market):
    return {key: market[key] for key in ('rules_primary', 'rules_secondary', 'close_time',
                                        'latest_expiration_time', 'settlement_timer_seconds')}


def book_url(source_id):
    return detail_url(source_id) + '/orderbook'


def validate_book(data):
    book = field(data, 'orderbook_fp', dict)
    for side in ('yes_dollars', 'no_dollars'):
        seen = set()
        for level in field(book, side, list):
            if not isinstance(level, list) or len(level) != 2:
                raise SchemaError('expected fixed-point [price,quantity]')
            price = decimal_value(level[0], price=True, positive=True)
            decimal_value(level[1], positive=True)
            if price >= 1 or price in seen:
                raise SchemaError('invalid or duplicate book price')
            seen.add(price)


def book_info(data):
    book = data['orderbook_fp']
    return None, (len(book['yes_dollars']), len(book['no_dollars']))
