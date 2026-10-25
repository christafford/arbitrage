"""Conservative NBA/NFL game-winner identity extraction, never payout approval.

Names are league-scoped aliases, not fuzzy guesses. Unsupported or incomplete
sports records cannot fall back to generic word overlap. Rule text supplies the
original scheduled calendar date; occurrence/start/settlement clocks stay separate.
"""
from datetime import date
from functools import lru_cache
import re


# Explicit reviewed team aliases. Ambiguous city-only LA/NY names are omitted.
# A pipe separates names; each row starts with our local canonical identity.
TEAM_ROWS = {
    'NBA': '''ATL|Atlanta|Hawks|Atlanta Hawks
BOS|Boston|Celtics|Boston Celtics
BKN|Brooklyn|Nets|Brooklyn Nets
CHA|Charlotte|Hornets|Charlotte Hornets
CHI|Chicago|Bulls|Chicago Bulls
CLE|Cleveland|Cavaliers|Cleveland Cavaliers
DAL|Dallas|Mavericks|Dallas Mavericks
DEN|Denver|Nuggets|Denver Nuggets
DET|Detroit|Pistons|Detroit Pistons
GSW|Golden State|Warriors|Golden State Warriors|GS|GS Warriors
HOU|Houston|Rockets|Houston Rockets
IND|Indiana|Pacers|Indiana Pacers
LAC|Los Angeles C|LA Clippers|Los Angeles Clippers|Clippers
LAL|Los Angeles L|LA Lakers|Los Angeles Lakers|Lakers
MEM|Memphis|Grizzlies|Memphis Grizzlies
MIA|Miami|Heat|Miami Heat
MIL|Milwaukee|Bucks|Milwaukee Bucks
MIN|Minnesota|Timberwolves|Minnesota Timberwolves
NOP|New Orleans|Pelicans|New Orleans Pelicans|NO|NO Pelicans
NYK|New York|Knicks|New York Knicks|NY|NY Knicks
OKC|Oklahoma City|Thunder|Oklahoma City Thunder
ORL|Orlando|Magic|Orlando Magic
PHI|Philadelphia|76ers|Philadelphia 76ers
PHX|Phoenix|Suns|Phoenix Suns|PHO|PHO Suns
POR|Portland|Trail Blazers|Portland Trail Blazers
SAC|Sacramento|Kings|Sacramento Kings
SAS|San Antonio|Spurs|San Antonio Spurs|SA|SA Spurs
TOR|Toronto|Raptors|Toronto Raptors
UTA|Utah|Jazz|Utah Jazz
WAS|Washington|Wizards|Washington Wizards|WSH''',
    'NFL': '''ARI|Arizona|Cardinals|Arizona Cardinals
ATL|Atlanta|Falcons|Atlanta Falcons
BAL|Baltimore|Ravens|Baltimore Ravens
BUF|Buffalo|Bills|Buffalo Bills
CAR|Carolina|Panthers|Carolina Panthers
CHI|Chicago|Bears|Chicago Bears
CIN|Cincinnati|Bengals|Cincinnati Bengals
CLE|Cleveland|Browns|Cleveland Browns
DAL|Dallas|Cowboys|Dallas Cowboys
DEN|Denver|Broncos|Denver Broncos
DET|Detroit|Lions|Detroit Lions
GB|Green Bay|Packers|Green Bay Packers
HOU|Houston|Texans|Houston Texans
IND|Indianapolis|Colts|Indianapolis Colts
JAC|Jacksonville|Jaguars|Jacksonville Jaguars|JAX
KC|Kansas City|Chiefs|Kansas City Chiefs
LAC|Los Angeles C|LA Chargers|Los Angeles Chargers|Chargers
LAR|Los Angeles R|LA Rams|Los Angeles Rams|Rams
LV|Las Vegas|Raiders|Las Vegas Raiders
MIA|Miami|Dolphins|Miami Dolphins
MIN|Minnesota|Vikings|Minnesota Vikings
NE|New England|Patriots|New England Patriots
NO|New Orleans|Saints|New Orleans Saints
NYG|New York G|NY Giants|New York Giants|Giants
NYJ|New York J|NY Jets|New York Jets|Jets
PHI|Philadelphia|Eagles|Philadelphia Eagles
PIT|Pittsburgh|Steelers|Pittsburgh Steelers
SEA|Seattle|Seahawks|Seattle Seahawks
SF|San Francisco|49ers|San Francisco 49ers
TB|Tampa Bay|Buccaneers|Tampa Bay Buccaneers
TEN|Tennessee|Titans|Tennessee Titans
WAS|Washington|Commanders|Washington Commanders|WSH''',
}


def words(value):
    return ' '.join(re.findall(r'[a-z0-9]+', value.lower())) if isinstance(value, str) else ''


@lru_cache(maxsize=2)
def aliases(league):
    result = {}
    for row in TEAM_ROWS[league].splitlines():
        code, *names = row.split('|')
        for name in [code, *names]:
            key = words(name)
            if key in result and result[key] != code:
                raise ValueError('ambiguous sports alias')
            result[key] = code
        # Explicit league abbreviations in US descriptions, e.g. MEM Grizzlies.
        for name in names:
            result.setdefault(words(code + ' ' + name), code)
    return result


def team(league, value):
    return aliases(league).get(words(value))


MONTHS = {name: i for i, full in enumerate(
    ('January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'), 1)
    for name in (full.lower(), full[:3].lower())}
DATE = re.compile(r'\bscheduled for ([a-z]+) (\d{1,2}), (20\d{2})\b', re.I)
K_GAME = re.compile(r'^If (.+?) wins the (.+?) vs (.+?) Pro (Football|Basketball) game originally scheduled for ', re.I)
US_GAME = re.compile(r'^This market will settle to the winner of the (.+?) vs (.+?) (NFL|professional football|professional basketball) game (?:originally )?scheduled for ', re.I)


def metadata(contract, key):
    return contract.get(key, contract.get('uninterpreted_metadata', {}).get(key))


def detected(contract):
    ticker = contract.get('ticker', '')
    title = words(contract.get('title', '') or contract.get('question', ''))
    rules = words(contract.get('rules_primary', ''))
    return (metadata(contract, 'category') == 'sports'
            or bool(metadata(contract, 'sportsMarketType'))
            or bool(metadata(contract, 'sportsMarketTypeV2'))
            or ticker.startswith(('KXNBAGAME-', 'KXNFLGAME-'))
            or contract.get('slug', '').startswith(('aec-nba-', 'aec-nfl-'))
            or title == 'both teams to score'
            or bool(re.search(r'\b(?:soccer|football|basketball|baseball|hockey|tennis) (?:game|match)\b', rules)))


def features(contract):
    if not detected(contract):
        return None
    result = {'supported': False, 'league': None, 'market_type': None, 'participants': [],
              'selection': None, 'scheduled_date': None, 'date_source': None,
              'postponement_window': 'UNKNOWN', 'issues': []}
    primary = contract.get('rules_primary', '')
    description = contract.get('description', '')
    k = K_GAME.match(primary)
    p = US_GAME.match(description)
    if k and contract.get('ticker', '').split('-')[0] in {'KXNBAGAME', 'KXNFLGAME'}:
        selected, left, right, sport = k.groups()
        league = 'NFL' if sport.lower() == 'football' else 'NBA'
        if contract['ticker'].split('-')[0] != 'KX' + league + 'GAME':
            result['issues'] = ['LEAGUE_CONFLICT']; return result
        text, source = primary, 'rules_primary'
    elif p and contract.get('slug', '').startswith('aec-'):
        left, right, sport = p.groups()
        league = 'NBA' if sport.lower() == 'professional basketball' else 'NFL'
        if not contract['slug'].startswith('aec-' + league.lower() + '-'):
            result['issues'] = ['LEAGUE_CONFLICT']; return result
        # These values were verified in official schemas and captured responses.
        # Unknown/new formats remain unsupported, even with a familiar title.
        expected = 'football_team_full_game_winner' if league == 'NFL' else 'basketball_team_full_game_winner'
        if metadata(contract, 'sportsMarketType') != expected:
            result['issues'] = ['UNSUPPORTED_MARKET_TYPE']; return result
        if metadata(contract, 'marketType') not in (None, 'moneyline'):
            result['issues'] = ['MARKET_TYPE_CONFLICT']; return result
        if metadata(contract, 'sportsMarketTypeV2') not in (None, 'SPORTS_MARKET_TYPE_MONEYLINE'):
            result['issues'] = ['MARKET_TYPE_CONFLICT']; return result
        sides = contract.get('marketSides', [])
        if (len(sides) != 2 or sum(s.get('long') is True for s in sides) != 1
                or sum(s.get('long') is False for s in sides) != 1
                or any(s.get('identifier') != contract['slug'] or
                       s.get('marketSideType') != 'MARKET_SIDE_TYPE_INSTRUMENT' for s in sides)):
            result['issues'] = ['UNSUPPORTED_SIDE_MAPPING']; return result
        side_teams = []
        for side in sides:
            info = side.get('team')
            if not isinstance(info, dict) or str(info.get('league', '')).upper() != league:
                result['issues'] = ['MISSING_OR_CONFLICTING_TEAM_LEAGUE']; return result
            name = team(league, info.get('name'))
            if name is None or team(league, side.get('description')) != name:
                result['issues'] = ['AMBIGUOUS_TEAM_SIDE']; return result
            side_teams.append(name)
            if side['long']: selected = info['name']
        if set(side_teams) != {team(league, left), team(league, right)}:
            result['issues'] = ['PARTICIPANT_SIDE_CONFLICT']; return result
        text, source = description, 'description'
    else:
        result['issues'] = ['UNSUPPORTED_SPORTS_FORMAT']; return result
    participants = [team(league, name) for name in (left, right)]
    selection = team(league, selected)
    result.update(league=league, market_type='FULL_GAME_WINNER', selection=selection)
    if None in participants or len(set(participants)) != 2 or selection not in participants:
        result['issues'] = ['UNKNOWN_OR_AMBIGUOUS_PARTICIPANTS']; return result
    if k and contract.get('yes_sub_title') is not None and team(league, contract['yes_sub_title']) != selection:
        result['issues'] = ['SELECTION_CONFLICT']; return result
    dates = set()
    try:
        for month, day, year in DATE.findall(text):
            dates.add(date(int(year), MONTHS[month.lower()], int(day)).isoformat())
    except (ValueError, KeyError):
        result['issues'] = ['INVALID_SCHEDULED_DATE']; return result
    if len(dates) != 1:
        result['issues'] = ['MISSING_OR_AMBIGUOUS_SCHEDULED_DATE']; return result
    result.update(supported=True, participants=sorted(participants), scheduled_date=dates.pop(), date_source=source)
    rules = words(primary + ' ' + contract.get('rules_secondary', '') + ' ' + description)
    windows = [label for phrase, label in [('within 48 hours', '48_HOURS'), ('within two weeks', 'TWO_WEEKS'),
                                          ('within two calendar days', 'TWO_CALENDAR_DAYS')] if phrase in rules]
    if len(windows) == 1: result['postponement_window'] = windows[0]
    return result


def key(sports):
    if not sports or not sports['supported']:
        return None
    return (sports['league'], sports['market_type'], tuple(sports['participants']),
            sports['scheduled_date'], sports['selection'])


def compare(left, right, *, min_score=0):
    a, b = left.get('sports'), right.get('sports')
    if key(a) is None or key(a) != key(b):
        return None
    warnings = ['SPORTS_IDENTITY_ONLY_NOT_EQUIVALENCE', 'SPORTS_SETTLEMENT_REVIEW_REQUIRED']
    score = 9000
    if a['postponement_window'] == 'UNKNOWN' or b['postponement_window'] == 'UNKNOWN':
        warnings.append('POSTPONEMENT_WINDOW_UNKNOWN'); score -= 500
    elif a['postponement_window'] != b['postponement_window']:
        warnings.append('POSTPONEMENT_WINDOW_CONFLICT' if 'TWO_WEEKS' in
                        {a['postponement_window'], b['postponement_window']} else 'POSTPONEMENT_WINDOW_INTERPRETATION_REQUIRED')
        score -= 1000
    if left['event_time'] != right['event_time']:
        warnings.append('OCCURRENCE_AND_START_TIMES_NOT_COMPARABLE')
    if left['cutoff'] != right['cutoff']:
        warnings.append('ADMINISTRATIVE_CUTOFFS_DIFFER')
    signals = {'subject_bps': 10000, 'sports_identity': 'MATCH', 'league': a['league'],
               'market_type': a['market_type'], 'participants': a['participants'],
               'selection': a['selection'], 'dates': 'SCHEDULED_RULE_DATE_MATCH',
               'settlement_equivalence': 'UNVERIFIED'}
    return (score, signals, warnings) if score >= min_score else None
