"""Fresh source-bound purposive election-day data-quality shortlist (UNVERIFIED)."""
import argparse
import hashlib
from pathlib import Path

from predarb import kalshi,polymarket_us as us
from predarb.conditional_research import contract_fingerprint
from predarb.orderbooks import market_rules,normalize_rest
from predarb.provider import HttpClient
from predarb.quality_capture import now
from predarb.soak import atomic_json
from predarb.store import connect
from predarb.validation import dumps

PROPOSALS=[('house-dem','CONTROLH-2026-D','paccc-usho-midterms-2026-11-03-dem'),
           ('senate-rep','CONTROLS-2026-R','paccc-usse-midterms-2026-11-03-rep')]


def select(root):
    root=Path(root);root.mkdir(parents=True,exist_ok=False)
    pairs=[];responses=[]
    with connect(str(root/'selection.sqlite3')) as con:
        clients={v:HttpClient(con,v,attempts=1,timeout=5,interval=1) for v in ('kalshi','polymarket_us')}
        for name,ticker,slug in PROPOSALS:
            fingerprints={};metrics={};sources=[]
            for venue,adapter,sid in [('kalshi',kalshi,ticker),('polymarket_us',us,slug)]:
                client=clients[venue]
                detail=client.get(adapter.detail_url(sid),adapter.SCHEMA_VERSION,adapter.validate_detail)
                market=detail.data['market'];market_rules(venue,sid,market,now=now())
                rawbook=client.get(adapter.book_url(sid),adapter.SCHEMA_VERSION,adapter.validate_book)
                book=normalize_rest(venue,sid,rawbook.data,market,received_at=rawbook.received_at,
                    metadata_received_at=detail.received_at,now=now())
                # Kalshi REST source clock is unknown; depth still proves displayed orders only.
                if not book.yes_asks or not book.no_asks:raise ValueError('selection requires valid two-sided displayed depth')
                if any(r!='UNKNOWN_SOURCE_TIME' for r in book.rejections):raise ValueError('invalid selection book')
                fingerprints[venue]=contract_fingerprint(venue,market)
                metrics[venue]=dict(volume_24h=market.get('volume_24h_fp') if venue=='kalshi' else market.get('volume24hr'),
                    yes_best=book.yes_asks[0].__dict__,no_best=book.no_asks[0].__dict__,
                    source_ts=book.source_ts,received_at=book.received_at,
                    activity_limit='Volume is not update cadence or executable liquidity; US missing volume remains UNKNOWN.')
                for observation in (detail,rawbook):
                    raw,digest=con.execute('SELECT raw_body,body_sha256 FROM raw_observations WHERE id=?',(observation.id,)).fetchone()
                    row=dict(venue=venue,source_id=sid,observation_id=observation.id,endpoint=observation.endpoint,
                        received_at=observation.received_at,schema_version=adapter.SCHEMA_VERSION,body=raw.decode(),sha256=digest,
                        representation='EXACT_PUBLIC_RESPONSE')
                    responses.append(row);sources.append({k:v for k,v in row.items() if k!='body'})
            pairs.append(dict(id=name,kalshi_id=ticker,polymarket_us_id=slug,classification='CONDITIONAL',
                ordinary_basis='Assistant ordinary-outcome screen: named party control of the same chamber following the November 3 2026 election. NOT legal equivalence.',
                residual_risks=['Kalshi early media-call determination versus US electoral/chamber sources',
                    'Kalshi February 1 officeholder fallback versus US majority/independent-caucus/January 4 attribution',
                    'Runoffs, party changes and ambiguous control can produce different payouts',
                    'Unreviewed fees, collateral, cash release and non-atomic fills'],
                exceptional_scenario='HYPOTHETICAL K YES=1, US YES=0: both selected legs pay zero; unadjudicated source differences.',
                origin='DETERMINISTIC',ai_only=False,contract_fingerprints=fingerprints,
                selection_metrics=metrics,sources=sources,operator_approved=False))
    manifest=dict(schema='m5p-selection/v1',selected_at=now().isoformat(),pairs=pairs,
        selection='Purposive two-chamber election-day scope, fresh open-state and two-sided depth. Not representative coverage; source activity must be measured.',
        inference_requests=0,strict_pairs=0,trading_authorized=False)
    atomic_json(root/'candidates.json',manifest)
    atomic_json(root/'fixture.json',dict(schema='m5p-public-selection/v1',hypothetical=False,responses=responses))
    print(dumps(manifest))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True)
    select(p.parse_args().output)
