"""HYPOTHETICAL M4 pipeline replay. No network, real approvals, funds or orders."""
import argparse
from datetime import timedelta
from pathlib import Path

from predarb import registry as r
from predarb.fee_store import import_profile
from predarb.research import archive_replay, export_csv, scan_once, start_session, summary
from predarb.store import connect
from predarb.validation import dumps, load_json, utc_time


def run(output, *, mechanics_fixture=None):
    root=Path(output);root.mkdir(parents=True,exist_ok=False)
    raw=Path('tests/fixtures/m4-hypothetical.json').read_bytes()
    # Original bytes are copied before parsing, then inserted as immutable replay evidence.
    (root/'inputs.json').write_bytes(raw)
    case=load_json(raw);assert case['hypothetical'] is True
    now=utc_time(case['clock'])
    (root/'HYPOTHETICAL-fees.txt').write_text('HYPOTHETICAL fee applicability for synthetic instruments only.\n')
    with connect(str(root/'research.sqlite3')) as con:
        replay_id=archive_replay(con,raw,now=now)
        r.load_hypothetical(con,case['registry'],now=now)
        pair_id=r.propose(con,'HYPOTHETICAL-K','HYPOTHETICAL-P','HYPOTHETICAL proposer',now=now)
        form=r.review_template(con,pair_id,now=now)
        form.update(reviewer='HYPOTHETICAL simulated reviewer',human_reviewed=True,
                    expires_at=(now+timedelta(hours=1)).isoformat(),reason='HYPOTHETICAL inverse propositions',
                    outcome_mapping={'YES':'NO','NO':'YES'},legs={'kalshi':'YES','polymarket_us':'YES'})
        for key in r.CHECKS:
            form['comparisons'][key]={'equivalent':True,'rationale':'HYPOTHETICAL terms compared explicitly: '+key}
        for code in r.SCENARIOS:
            normal=code in {'YES','NO'}
            form['settlement_scenarios'].append({
                'case':code,'condition':'HYPOTHETICAL '+code,
                'kalshi_payout':('1' if code=='YES' else '0') if normal else '0.50',
                'polymarket_us_payout':('0' if code=='YES' else '1') if normal else '0.50',
                'kalshi_settlement_at':'2030-07-04T12:00:00Z','polymarket_us_settlement_at':'2030-07-04T12:00:00Z'})
        if mechanics_fixture:
            mechanics_raw=Path(mechanics_fixture).read_bytes()
            (root/'mechanics-input.json').write_bytes(mechanics_raw)
            mechanics_case=load_json(mechanics_raw)
            if (mechanics_case.get('hypothetical') is not True or
                    mechanics_case.get('schema') != 'm5d-hypothetical/v1' or
                    mechanics_case.get('clock') != case['clock']):
                raise ValueError('matching explicitly hypothetical M5D fixture required')
            form=mechanics_case['review']
        r.approve(con,pair_id,form,human_attested=True,now=now)
        for profile in case['fee_profiles']:
            import_profile(con,dumps(profile).encode(),base=root,now=now,attested=True)
        session_id=start_session(con,case['policy'],interval_seconds=30,now=now,hypothetical=True)
        cycles=[scan_once(con,session_id,now=now,replay_id=replay_id),
                scan_once(con,session_id,now=now+timedelta(seconds=30),replay_id=replay_id)]
        favorable=summary(con,session_id)
        best=favorable['latest_ranked_independent_alternatives'][0]['best']
        assert best['contracts']=='200' and best['net_profit_bound'].rstrip('0')=='16.54'
        cycles.append(scan_once(con,session_id,now=now+timedelta(seconds=61),replay_id=replay_id))
        assert cycles[-1]['rejected']==1
        report=summary(con,session_id)
        (root/'evaluations.csv').write_text(export_csv(con,session_id))
    result={'hypothetical':True,'historical_replay':True,'cycles':cycles,'favorable_sample':best,
            'report':report,'trading_authorized':False,'thirty_day_acceptance':False}
    (root/'results.json').write_text(dumps(result)+'\n')
    print(dumps(result))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True)
    parser.add_argument('--mechanics-fixture',help='optional M5D HYPOTHETICAL source-bound mechanics review')
    args=parser.parse_args()
    run(args.output,mechanics_fixture=args.mechanics_fixture)
