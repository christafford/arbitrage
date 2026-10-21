"""US retail gateway MarketService 1.0.0; no international or institutional fallback."""
import os
from urllib.parse import urlencode
from .validation import (SchemaError, amount, decimal_value, field, identifier,
                         text_field, utc_time)

BASE = 'https://gateway.polymarket.us'
SCHEMA_VERSION = 'polymarket-us-marketservice-1.0.0/m1-v1'
VENUE = 'polymarket_us'
ID_FIELD = 'slug'
TIME_FIELD = 'updatedAt'


def base_url():
    if os.environ.get('POLYMARKET_US_DATA_BASE', BASE).rstrip('/') != BASE:
        raise ValueError('POLYMARKET_US_DATA_BASE must be the verified US public gateway: ' + BASE)
    return BASE


def page_url(page_size, continuation, scope):
    params = {'active': 'true', 'closed': 'false', 'limit': page_size,
              'offset': int(continuation or 0), 'orderBy': 'id', 'orderDirection': 'asc'}
    if scope:
        params['slug'] = identifier(scope)
    return base_url() + '/v1/markets?' + urlencode(params)


def validate_market(market):
    text_field(market, 'id')
    identifier(text_field(market, 'slug'))
    text_field(market, 'question')
    text_field(market, 'description', empty=True)
    for key in ('active', 'closed'):
        field(market, key, bool)
    for key in ('createdAt', 'updatedAt', 'endDate'):
        utc_time(text_field(market, key))
    if text_field(market, 'status') not in {
        'MARKET_STATUS_UNSPECIFIED', 'MARKET_STATUS_OPEN', 'MARKET_STATUS_CLOSED',
        'MARKET_STATUS_RESOLVING', 'MARKET_STATUS_RESOLVED', 'MARKET_STATUS_HALTED'}:
        raise SchemaError('unknown market status')
    sides = field(market, 'marketSides', list)
    if not sides:
        raise SchemaError('missing instrument side metadata')
    side_ids = set()
    for side in sides:
        side_id = text_field(side, 'id')
        if side_id in side_ids:
            raise SchemaError('duplicate market side')
        side_ids.add(side_id)
        text_field(side, 'marketSideType')
        identifier(text_field(side, 'identifier'))
        field(side, 'long', bool)
        if 'price' in side and side['price'] is not None:
            decimal_value(side['price'], price=True)
        if 'quote' in side and side['quote'] is not None:
            amount(side['quote'])
    for key in ('bestBidQuote', 'bestAskQuote'):
        if key in market and market[key] is not None:
            amount(market[key])
    for key in ('orderPriceMinTickSize', 'minimumTradeQty'):
        if key in market and market[key] is not None:
            decimal_value(market[key], positive=True, string=False)
    # Opaque metadata and asset-specific terms are retained verbatim, not interpreted.


def validate_page(data):
    for market in field(data, 'markets', list):
        validate_market(market)


def next_page(data, current, page_size):
    count = len(data['markets'])
    # Only an empty page proves exhaustion; a server may cap a requested page size.
    return str(int(current or 0) + count) if count else None


def detail_url(source_id):
    return base_url() + '/v1/market/slug/' + identifier(source_id)


def validate_detail(data):
    validate_market(field(data, 'market', dict))


def rules(market):
    # These are provider evidence, not an assertion that description is the full legal contract.
    return {key: market[key] for key in ('description', 'endDate', 'assetPriceTerms', 'rulesDisclaimer')
            if key in market}


def book_url(source_id):
    return base_url() + '/v1/markets/' + identifier(source_id) + '/book'


def validate_book(data):
    book = field(data, 'marketData', dict)
    identifier(text_field(book, 'marketSlug'))
    utc_time(text_field(book, 'transactTime'))
    if text_field(book, 'state') not in {
        'MARKET_STATE_OPEN', 'MARKET_STATE_PREOPEN', 'MARKET_STATE_SUSPENDED', 'MARKET_STATE_EXPIRED',
        'MARKET_STATE_TERMINATED', 'MARKET_STATE_HALTED', 'MARKET_STATE_MATCH_AND_CLOSE_AUCTION'}:
        raise SchemaError('unknown book state')
    for side in ('bids', 'offers'):
        seen = set()
        for level in field(book, side, list):
            price = amount(field(level, 'px', dict))
            if not 0 < price < 1 or price in seen:
                raise SchemaError('invalid or duplicate book price')
            seen.add(price)
            decimal_value(text_field(level, 'qty'), positive=True)


def book_info(data):
    book = data['marketData']
    return book['transactTime'], (len(book['bids']), len(book['offers']))
