"""M5Q offline quote discrepancies. No approvals, fills or production gate changes."""
from dataclasses import asdict
from decimal import Decimal, localcontext
import hashlib

from .conditional_research import classification, quote_cases
from .orderbooks import walk_depth
from .quality_capture import seconds
from .validation import dumps, utc_time

VERSION = 'economic-signal-validation/m5q-v1'


def reconstruct(books, pair, *, at, inspected, provenance):
    """Apply existing quality/mechanics math under an explicit ordinary-payout premise.

    DISCOVERY may measure a price discrepancy but never gains a conditional or
    strict classification. The premise is arithmetic, not a settlement decision.
    """
    group = classification(pair)
    premise = dict(pair, classification='CONDITIONAL', ordinary_basis=
                   'HYPOTHETICAL arithmetic premise: selected legs pay one dollar combined')
    result = quote_cases(books, premise, now=at, inspected=inspected)
    result.update(schema=VERSION, classification=group, at=at.isoformat(),
                  provenance=provenance, ordinary_basis=pair.get('ordinary_basis', 'UNKNOWN'),
                  settlement_review='PENDING', fee_status='UNKNOWN_UNREVIEWED',
                  expected_settlement_at=None, expected_capital_release_at=None)
    result['status'] = ('DISCOVERY_QUOTE_DISCREPANCY' if group == 'DISCOVERY' else
                        'CONDITIONAL_GROSS_ONLY') if result['capital_cases'] else 'REJECTED_DATA_QUALITY'
    depth = [[[(x.price, x.quantity) for x in levels]
              for levels in (b.yes_asks,b.no_asks)] for b in books]
    # Receipt refresh and transport messages cannot manufacture a new depth state.
    result['depth_state_sha256'] = hashlib.sha256(dumps(depth).encode()).hexdigest()
    result['source_state_sha256'] = hashlib.sha256(dumps([
        dict(venue=b.venue, source_id=b.source_id, source_ts=b.source_ts,
             depth=d, source_version=pair['contract_fingerprints'][b.venue])
        for b,d in zip(books,depth)]).encode()).hexdigest()
    result['source_versions'] = pair['contract_fingerprints']
    result['displayed_books'] = [b.as_dict(now=at) for b in books]
    with localcontext() as ctx:
        ctx.prec = 80
        for case in result['capital_cases']:
            q = case['evaluated_quantity']
            case['positive_gross_signal'] = case.pop('positive_conditional_discrepancy')
            legs = [walk_depth(b,s,q,now=at) for b,s in zip(books,('NO','YES'))] if q else []
            case['displayed_depth_walks'] = [asdict(d) for d in legs]
            case['gross_edge_per_unit_usd'] = case['gross_edge_usd']/q if q else None
            case['gross_return_on_quote_cost'] = (case['gross_edge_usd']/case['prefee_capital_usd']
                                                 if case['prefee_capital_usd'] else None)
            case['one_leg_only_loss_before_fees_usd'] = case['prefee_capital_per_venue_usd']
            case['one_leg_unmatched_quantity'] = q
            case['partial_fill_exposure'] = 'For unequal fills, abs(q_k-q_us) units remain unhedged; either single leg can lose its entire purchase cost plus UNKNOWN fees.'
            case['actual_fills'] = None
            case['buying_power_required_usd'] = None
            case['additional_collateral_required_usd'] = None
    return result


class Episodes:
    """Sample clusters, not continuous duration or independent statistical trials."""
    def __init__(self, max_gap_seconds=Decimal('2')):
        if not isinstance(max_gap_seconds,Decimal) or not 0 < max_gap_seconds <= 2:
            raise ValueError('episode gap must be Decimal in (0,2]')
        self.gap = max_gap_seconds
        self.rows = []
        self.current = None
        self.previous_at = None
        self.states = set()
        self.depths = set()

    def add(self, row):
        at = utc_time(row['at'])
        if self.previous_at is not None and at <= self.previous_at:
            raise ValueError('observation times must strictly increase')
        self.previous_at = at
        positive = [c for c in row.get('capital_cases',[]) if c['positive_gross_signal']]
        if not row.get('quality',{}).get('timestamp_depth_overlap') or not positive:
            self.current = None
            return
        identity = (row['classification'],dumps(row['source_versions']))
        best = max(positive,key=lambda c:Decimal(c['gross_edge_usd']))
        if (self.current is None or self.current['_identity'] != identity or
            seconds(at-utc_time(self.current['last_at'])) > self.gap):
            self.current = dict(_identity=identity,first_at=row['at'],last_at=row['at'],
                samples=0,source_states=set(),depth_states=set(),classification=row['classification'],
                max_gross_edge_usd=Decimal(0),best_observation=None)
            self.rows.append(self.current)
        current=self.current
        current['last_at']=row['at']; current['samples']+=1
        current['source_states'].add(row['source_state_sha256'])
        current['depth_states'].add(row['depth_state_sha256'])
        self.states.add(row['source_state_sha256']); self.depths.add(row['depth_state_sha256'])
        if Decimal(best['gross_edge_usd']) > current['max_gross_edge_usd']:
            current['max_gross_edge_usd']=Decimal(best['gross_edge_usd'])
            current['best_observation']=row

    def report(self):
        return [dict(first_at=r['first_at'],last_at=r['last_at'],samples=r['samples'],
            sampled_span_seconds=seconds(utc_time(r['last_at'])-utc_time(r['first_at'])),
            distinct_source_states=len(r['source_states']),distinct_depth_states=len(r['depth_states']),
            classification=r['classification'],max_gross_edge_usd=r['max_gross_edge_usd'],
            best_observation=r['best_observation'],continuous_opportunity_seconds=None,
            duration_limit='Sample span only; gaps <=2s do not establish continuity or fills.') for r in self.rows]
