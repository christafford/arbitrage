"""Versioned, fail-closed validation of fields consumed by catalogue collectors."""
import json
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation


class SchemaError(ValueError):
    pass


def object_value(value):
    if not isinstance(value, dict):
        raise SchemaError('expected JSON object')
    return value


def field(obj, key, kind):
    object_value(obj)
    if key not in obj or type(obj[key]) is not kind:
        raise SchemaError(f'missing or invalid {key}: expected {kind.__name__}')
    return obj[key]


def text_field(obj, key, *, empty=False):
    value = field(obj, key, str)
    if not empty and not value.strip():
        raise SchemaError(f'empty {key}')
    return value


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,250}', value):
        raise ValueError('invalid source identifier')
    return value


def utc_time(value):
    if not isinstance(value, str):
        raise SchemaError('timestamp must be an ISO 8601 string')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise SchemaError('invalid timestamp') from exc
    if parsed.tzinfo is None:
        raise SchemaError('timestamp must have an explicit timezone')
    return parsed.astimezone(timezone.utc)


def decimal_value(value, *, price=False, positive=False, string=True):
    if string and not isinstance(value, str):
        raise SchemaError('expected decimal string')
    if isinstance(value, (bool, float)) or not isinstance(value, (str, int, Decimal)):
        raise SchemaError('invalid decimal type')
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise SchemaError('invalid decimal') from exc
    if not number.is_finite() or number < 0 or (positive and number <= 0):
        raise SchemaError('nonfinite, negative or zero decimal')
    if price and number > 1:
        raise SchemaError('price outside [0,1]')
    return number


def amount(value):
    if text_field(value, 'currency') != 'USD':
        raise SchemaError('unsupported currency')
    return decimal_value(text_field(value, 'value'), price=True)


def dumps(value):
    # Exact decimals in derived metadata are strings; raw bytes remain unchanged.
    return json.dumps(value, default=lambda x: str(x) if isinstance(x, Decimal) else _unsupported(x),
                      sort_keys=True, separators=(',', ':'), allow_nan=False)


def _unsupported(value):
    raise TypeError(type(value).__name__)


def load_json(body):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise SchemaError(f'duplicate JSON key: {key}')
            result[key] = value
        return result
    def reject(value):
        raise SchemaError(f'nonstandard JSON constant: {value}')
    try:
        return json.loads(body, parse_float=Decimal, parse_constant=reject, object_pairs_hook=unique)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SchemaError('response is not valid UTF-8 JSON') from exc
