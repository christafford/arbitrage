"""Conservative explicit proposition conflicts, never equivalence approval.

Only recognized assertions are compared. Unknown language stays unknown; these
bounded heuristics are not a complete parser of exchange settlement rules.
"""
from decimal import Decimal
from functools import lru_cache
import json
import re
import unicodedata

VERSION = 'proposition-guards/m5i-v3'
FIELDS = ('rules_primary', 'description', 'rules_secondary', 'title', 'question', 'subtitle', 'yes_sub_title')
NUMBER = r'-?\d+(?:,\d{3})*(?:\.\d+)?'
SCALE = r'(?:trillion|billion|million|thousand|bn|tn|[kmbt])\b'
UNIT = r'(?:basis points|bps|percent|%|dollars|usd|points|degrees celsius|degrees fahrenheit)'
AMOUNT = rf'(?P<currency>\$)?\s*(?P<number>{NUMBER})\s*(?P<scale>{SCALE})?\s*(?P<unit>{UNIT})?'
OPS = {'greater than or equal to': '>=', 'less than or equal to': '<=',
       'more than or equal to': '>=', 'at least': '>=', 'at most': '<=',
       'no more than': '<=', 'no less than': '>=', 'not above': '<=', 'not below': '>=',
       'greater than': '>', 'more than': '>', 'less than': '<', 'lower than': '<', 'fewer than': '<',
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


def interval(text, all_text):
    """Explicit bounded range; never infer endpoint inclusion from 'between'."""
    def amount(suffix):
        return re.sub(r'\(\?P<(\w+)>', lambda m: '(?P<'+m[1]+suffix+'>', AMOUNT)
    matches = list(re.finditer(r'\bbetween\s+'+amount('a')+r'\s+(?:and|to)\s+'+amount('b'), text))
    if len(matches)!=1 or re.search(r'\bor\b', text):return None
    parts=matches[0].groupdict();ends=[]
    for suffix in ('a','b'):
        unit='USD' if parts['currency'+suffix] else UNITS.get(parts['unit'+suffix])
        value=Decimal(parts['number'+suffix].replace(',',''))*SCALES.get(parts['scale'+suffix],1)
        ends.append((value,unit))
    # Share an explicit unit, but not a magnitude: '1 to 2 million' is ambiguous.
    if parts['scalea']!=parts['scaleb']:return None
    unit=ends[0][1] or ends[1][1]
    if not unit or (ends[0][1] and ends[1][1] and ends[0][1]!=ends[1][1]) or ends[0][0]>ends[1][0]:return None
    inclusive=True if (re.search(r'\ball stated bounds are inclusive\b',all_text) or
                              re.search(r'\binclusive\b',text[matches[0].end():])) else None
    return {'lower':format(ends[0][0].normalize(),'f'),'upper':format(ends[1][0].normalize(),'f'),
            'unit':unit,'inclusive':inclusive}


def context_facets(text, all_text):
    """Narrow assertion grammars; unrecognized/compound subjects stay unknown."""
    kinds=set();geographies=set();person=country=departure=None
    if re.search(r'\b(?:gdp|gross domestic product)\b',text) and 'growth' in text:kinds.add('GDP_GROWTH')
    gas=bool(re.search(r'\b(?:gas prices?|price.{0,50}\bgas)\b',text))
    if gas:
        kinds.add('GAS_PRICE')
        if re.search(r'\b(?:us national|national average.{0,40}\b(?:us|united states))\b',text):geographies.add('US')
        if re.search(r'\b(?:for|in) california\b',text):geographies.add('US_CA')
    music=bool(re.search(r'\b(?:song|album|artist)s?\b',text))
    if music and 'spotify' in text and re.search(r'\b(?:streamed|ranked|ranking|top)\b',text):
        kinds.add('MUSIC_STREAM_RANK')
        if re.search(r'\b(?:globally|global)\b',text):geographies.add('GLOBAL')
        if re.search(r'\b(?:in the us|usa|united states)\b',text):geographies.add('US')
    if music and re.search(r'\bgrammy\b',text) and re.search(r'\bwins?\b',text):kinds.add('MUSIC_AWARD_WIN')
    match=re.search(r'^(?:if|this market will settle to yes if)\s+(.{1,90}?)\s+(?:leaves as|formally ceases to hold|has either officially announced)',text)
    if match and re.search(r'\bpresident of\b',text):
        kinds.add('OFFICE_DEPARTURE')
        name=match[1]
        if (2<=len(name.split())<=5 and re.fullmatch(r"[^\W\d_]+(?:[-' ][^\W\d_]+)+",name)
                and not re.search(r'\b(?:and|or|not|if|the|someone|anyone|either)\b',name)):
            person=name
        place=re.search(r'\bpresident of ([a-z ]{2,50}?)\s+(?:before|by|or|then|on)\b',text)
        if place and not re.search(r'\b(?:and|or|not)\b',place[1]):country=place[1].strip()
        if 'has either officially announced' in text:departure='ANNOUNCEMENT_OR_ACTUAL'
        elif 'formally ceases to hold' in text:departure='ACTUAL_DEPARTURE'
        elif 'based on the announcement date, regardless of effective date' in all_text:departure='ANNOUNCEMENT_DATE'
    return {'event_kind':next(iter(kinds)) if len(kinds)==1 else None,
            'geography':next(iter(geographies)) if len(geographies)==1 else None,
            'named_subject':person,'office_country':country,'departure_basis':departure}


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
    definition = re.sub(r'\bU\.S\.(?=\s)', 'US', definition, flags=re.IGNORECASE)
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
    # Parse the asserted proposition, never examples/contingencies later in rules.
    state_senate = bool(re.search(r'\bstate senate\b', text))
    us_senate = bool(re.search(r'\b(?:u\.?s\.?|united states)\s+senat(?:e|or)\b', text))
    office = ('STATE_SENATE' if state_senate else 'US_SENATE') if state_senate != us_senate else None
    company = action = None
    roles = re.findall(r'\b(?:ceo|chief executive officer)\s+(?:of|for|at)\s+(x|twitter|tesla)\b', text)
    companies = {'X' if name in ('x','twitter') else 'TESLA' for name in roles}
    if len(companies)==1:
        company = companies.pop()
        departure = bool(re.search(r'\b(?:departure|departs?|leaves?|resigns?|removed|out as)\b', text))
        appointment = bool(re.search(r'\b(?:confirmed|appointed|becomes?|named|next)\b', text))
        # Both/negated assertions are ambiguous; don't guess an action.
        negated = bool(re.search(r"\b(?:not|never|won't|doesn't)\b", text))
        if departure != appointment and not negated:
            action = 'DEPARTURE' if departure else 'APPOINTMENT'
    position = None
    if 'spotify' in text and re.search(r'\b(?:song|artist|album)s?\b', text):
        ranks = set(re.findall(r'#\s*(\d+)\b|\b(?:number|no\.)\s*(\d+)\b', text))
        numbers = {int(a or b) for a,b in ranks}
        ordinals = {'first':1,'second':2,'third':3}
        for word in re.findall(r'\b(first|second|third)(?:[- ]ranked| most streamed)\b', text):
            numbers.add(ordinals[word])
        if re.search(r'\b(?:the top|top-ranked|first-ranked|number one|#\s*1)\s+(?:song|artist|album)\b', text):
            numbers.add(1)
        if len(numbers)==1:position=str(numbers.pop())
    rate_direction = None
    if rate:
        unchanged = bool(re.search(r'\b(?:does not change|no change|unchanged|maintains? (?:the )?rates?)\b', text))
        hike = bool(re.search(r'\b(?:hike|hikes|increase|increases|raise|raises)\b', text))
        cut = bool(re.search(r'\b(?:cut|cuts|decrease|decreases|reduce|reduces|lower|lowers)\b', text))
        negated = bool(re.search(r"\b(?:not|never|won't|doesn't)\s+(?:hike|increase|raise|cut|decrease|reduce|lower)\b", text))
        if sum((unchanged,hike,cut))==1 and not negated:
            rate_direction = 'UNCHANGED' if unchanged else 'HIKE' if hike else 'CUT'
    return {'version':VERSION,'thresholds':values,'interval':interval(text,all_text),
            **context_facets(text,all_text),'observation_window':window,
            'proposition_type':scope,'rounding':rounding,'political_office':office,
            'ceo_company':company,'ceo_action':action,'ranking_position':position,
            'rate_direction':rate_direction}


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
    # A bounded interval versus a one-sided threshold differs even when they
    # overlap. Unknown inclusivity alone is never a conflict.
    def bounds(item):
        bounded=item.get('interval')
        if bounded:return (bounded['lower'],bounded['upper'],bounded['unit'],bounded['inclusive'],bounded['inclusive'])
        values=item['thresholds']
        if len(values)!=1 or values[0][2]=='unspecified':return None
        op,value,unit=values[0]
        return (value if op in ('>','>=','=') else None,value if op in ('<','<=','=') else None,
                unit,op in ('>=','='),op in ('<=','='))
    if left.get('interval') or right.get('interval'):
        a_range,b_range=bounds(left),bounds(right)
        if a_range and b_range and a_range[2]==b_range[2]:
            if a_range[:2]!=b_range[:2] or any(a is not None and b is not None and a!=b for a,b in zip(a_range[3:],b_range[3:])):
                warnings.append('PROPOSITION_RANGE_CONFLICT')
        else:warnings.append('PROPOSITION_RANGE_UNKNOWN')
    def directions(values):
        return {'LOWER_BOUND' if x[0].startswith('>') else 'UPPER_BOUND' if x[0].startswith('<') else 'EXACT' for x in values}
    left_direction, right_direction = directions(a), directions(b)
    if ((left_direction == {'LOWER_BOUND'} and right_direction == {'UPPER_BOUND'}) or
            (left_direction == {'UPPER_BOUND'} and right_direction == {'LOWER_BOUND'})):
        warnings.append('PROPOSITION_DIRECTION_CONFLICT')
    for facet in ('observation_window','proposition_type','rounding','political_office',
                  'ceo_company','ceo_action','ranking_position','rate_direction',
                  'event_kind','geography','named_subject','office_country','departure_basis'):
        a,b=left[facet],right[facet]
        if a and b and a!=b:warnings.append(facet.upper()+'_CONFLICT')
        elif bool(a)!=bool(b):warnings.append(facet.upper()+'_UNKNOWN')
    return warnings
