"""Conservative explicit proposition conflicts, never equivalence approval.

Only recognized assertions are compared. Unknown language stays unknown; these
bounded heuristics are not a complete parser of exchange settlement rules.
"""
from decimal import Decimal
from functools import lru_cache
import json
import re
import unicodedata

VERSION = 'proposition-guards/m5i-v1'
FIELDS = ('rules_primary', 'description', 'rules_secondary', 'title', 'question', 'subtitle', 'yes_sub_title')
NUMBER = r'-?\d+(?:,\d{3})*(?:\.\d+)?'
SCALE = r'(?:trillion|billion|million|thousand|bn|tn|[kmbt])\b'
UNIT = r'(?:basis points|bps|percent|%|dollars|usd|points|degrees celsius|degrees fahrenheit)'
AMOUNT = rf'(?P<currency>\$)?\s*(?P<number>{NUMBER})\s*(?P<scale>{SCALE})?\s*(?P<unit>{UNIT})?'
OPS = {'greater than or equal to': '>=', 'less than or equal to': '<=',
       'more than or equal to': '>=', 'at least': '>=', 'at most': '<=',
       'no more than': '<=', 'no less than': '>=', 'not above': '<=', 'not below': '>=',
       'greater than': '>', 'more than': '>', 'less than': '<', 'fewer than': '<',
       'above': '>', 'below': '<', 'over': '>', 'under': '<', 'exceeds': '>',
       'exceed': '>', '>=': '>=', '<=': '<=', '>': '>', '<': '<', 'exactly': '='}
PREFIX = re.compile(r'(?<!\w)(?P<operator>' + '|'.join(re.escape(x) for x in OPS) + r')\s*' + AMOUNT)
POSTFIX = re.compile(r'(?<![\w.])' + AMOUNT + r'\s+or\s+(?P<operator>below|less|lower|above|more|higher)\b')
SCALES = {'k':1000,'thousand':1000,'m':1000000,'million':1000000,
          'b':1000000000,'bn':1000000000,'billion':1000000000,
          't':1000000000000,'tn':1000000000000,'trillion':1000000000000}
UNITS = {'dollars':'USD','usd':'USD','percent':'%','%':'%', 'basis points':'bps',
         'bps':'bps','points':'points','degrees celsius':'C','degrees fahrenheit':'F'}


def normalized(text):
    text = text.replace('≥', '>=').replace('≤', '<=')
    return unicodedata.normalize('NFKC', text).lower()


def thresholds(text):
    result = set()
    for pattern in (PREFIX, POSTFIX):
        for match in pattern.finditer(normalized(text)):
            parts = match.groupdict()
            value = Decimal(parts['number'].replace(',', '')) * SCALES.get(parts['scale'], 1)
            unit = 'USD' if parts['currency'] else UNITS.get(parts['unit'], 'unspecified')
            operator = (('<=' if parts['operator'] in ('below','less','lower') else '>=')
                        if pattern is POSTFIX else OPS[parts['operator']])
            result.add((operator, format(value.normalize(), 'f'), unit))
    return sorted(result)


def extract(contract):
    texts = []
    for key in FIELDS:
        value = contract.get(key, '')
        if not isinstance(value, str):
            raise ValueError('proposition text must be a string: ' + key)
        texts.append(value)
    # Provider settlement assertion takes precedence over broad question/title
    # wording. Stop at the first sentence without splitting decimal amounts.
    definition = contract.get('rules_primary') or contract.get('description') or ''
    assertion = re.split(r'\n|(?<=[.!?])\s+(?=[A-Z])', definition, maxsplit=1)[0]
    selected = ' '.join(contract.get(k,'') for k in ('title','question','subtitle','yes_sub_title'))
    primary = assertion or selected
    values = thresholds(primary) or thresholds(selected)
    text = normalized(primary)
    all_text = normalized(' '.join(texts))
    scope = None
    rate = bool(re.search(r'\b(federal reserve|fomc|fed)\b', all_text))
    if rate and not values:
        amounts = re.findall(r'\b(?:by|of)\s+(' + NUMBER + r')\s*(?:basis points|bps)\b', text)
        direction = -1 if re.search(r'\b(cut|cuts|decrease|decreases|reduces|reduce)\b', text) else 1
        if amounts:
            values = [('=',format((Decimal(n.replace(',',''))*direction).normalize(),'f'),'bps') for n in amounts]
    if re.search(r'\bsupreme court\b', all_text):
        if re.search(r'\b(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+(?:supreme court\s+)?justices?\b', text) and re.search(r'\b(confirm|confirmed|confirmations?)\b', text):
            scope = 'CONFIRMATION_COUNT'
        elif re.search(r'\bnext\b', text) and re.search(r'\b(person|justice)\b', text):
            scope = 'NEXT_APPOINTEE'
    anytime = bool(re.search(r'\bat any (?:point|time)\b|\bat least once\b|\bstarting\b.+\bbefore\b', text))
    instant = bool(re.search(r'\bas of\b|\bat\s+\d{1,2}:\d{2}\s*(?:am|pm|et|utc)\b|\bclosing price\b', text))
    # A window may contain explicit clock times for its endpoints. They do not
    # turn an "at any point"/"starting ... before" assertion into a point sample.
    window = 'ANY_TIME' if anytime else 'POINT_IN_TIME' if instant else None
    rounded = bool(re.search(r'\bround(?:ed|ing)\b', all_text) and re.search(r'\b(?:displayed|nearest|options?|buckets?)\b', all_text))
    rounding = 'DISPLAYED_BUCKETS' if rounded else 'EXACT_STATED_CHANGE' if rate and any(v[0]=='=' and v[2]=='bps' for v in values) else None
    return {'version':VERSION,'thresholds':values,'observation_window':window,
            'proposition_type':scope,'rounding':rounding}


@lru_cache(maxsize=512)
def from_public_text(text):
    # The existing public-contract serialization is bounded at 16,000 bytes.
    if not isinstance(text,str) or len(text.encode())>16000:
        raise ValueError('missing or oversized proposition evidence')
    payload = json.loads(text)
    if payload.get('schema') != 'public-market-text/v1':
        raise ValueError('unknown public proposition schema')
    return extract(payload['public_contract'])


def compare(left, right):
    warnings = []
    if not left or not right or left.get('version')!=VERSION or right.get('version')!=VERSION:
        return ['PROPOSITION_EVIDENCE_UNKNOWN']
    a,b=left['thresholds'],right['thresholds']
    # Compare only equally typed, explicit units. Unknown is never USD by guess.
    typed_a={tuple(x) for x in a if x[2]!='unspecified'}
    typed_b={tuple(x) for x in b if x[2]!='unspecified'}
    if typed_a and typed_b and typed_a!=typed_b:
        warnings.append('PROPOSITION_THRESHOLD_CONFLICT')
    elif bool(typed_a)!=bool(typed_b):
        warnings.append('PROPOSITION_THRESHOLD_UNKNOWN')
    def directions(values):
        return {'LOWER_BOUND' if x[0].startswith('>') else 'UPPER_BOUND' if x[0].startswith('<') else 'EXACT' for x in values}
    left_direction, right_direction = directions(a), directions(b)
    if ((left_direction == {'LOWER_BOUND'} and right_direction == {'UPPER_BOUND'}) or
            (left_direction == {'UPPER_BOUND'} and right_direction == {'LOWER_BOUND'})):
        warnings.append('PROPOSITION_DIRECTION_CONFLICT')
    for facet in ('observation_window','proposition_type','rounding'):
        a,b=left[facet],right[facet]
        if a and b and a!=b:warnings.append(facet.upper()+'_CONFLICT')
        elif bool(a)!=bool(b):warnings.append(facet.upper()+'_UNKNOWN')
    return warnings
