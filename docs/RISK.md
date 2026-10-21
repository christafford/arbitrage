# Risk controls and funding policy

## Financial constraints

- Initial phase: $0 at risk. First authorized trial should be at most $200–$500 funded total, with tiny per-pair sizes and a separate formal go/no-go.
- Cumulative seed deposits from outside accounts across all venues: **$10,000 maximum**; profits do NOT silently expand the amount at risk. Require a deliberate policy revision to reinvest above risk caps.
- No margin, leverage, borrowing, automatic top-ups, short naked legs, or speculative direction-taking as fallback.
- Funding balance and **worst-case open exposure** must be measured separately; counting matched pairs alone hides temporary unhedged risk.
- Set future runtime limits for per-leg order notional, per-pair notional, aggregate unhedged exposure, per-venue allocation, daily loss and outstanding order commitments. Treat absent configuration as zero trading permission.

## Settlement equivalence gate

Every pair needs independent human review of official rules: proposition, event definition, timing/timezone, cutoff, resolution source, thresholds, revisions, market suspension, cancellation/voids, and payout semantics. Record source URLs, fetched text hashes, approval identity/time, and invalidate approval if either rule set changes. A title similarity or LLM verdict does not qualify.

## Quote and fill risks

Only compute on fresh, executable ask ladders. Apply actual fee schedules, price/size increments, slippage reserve, partial fills, fee rounding, withdrawal/transfer frictions, and settlement delays. Record assumptions separately from measured fields. Define conservatively how to count capital tied up across venues.

## Future execution gate (not built)

Before live orders: operator authorization, production-vs-demo environment confirmation, allowlisted instruments, dry-run parity, append-only order intent journal, idempotency, deterministic reconciliation after crash, max hedge delay, cancel/reprice policies, liquidation plan if only one leg fills, manual kill switch, and no-go thresholds. Treat venue outage/settlement failure as possible loss even in theoretically hedged structures.

## Operational security

No API secrets in repo/logs. Minimum permissions (prefer dedicated read-only keys where available). Least-privilege process, TLS verification, time synchronization, database backups, disk alarms, and 2FA where supported. Never expose order endpoints or dashboards to the public internet without a documented security plan.

## Taxes & access

Verify accounts and contract eligibility for your actual jurisdiction before funding. U.S. venue access and contract availability are not identical. Consult qualified tax advice for realized gains, reporting and treatment; software must retain raw trades and settlements if trading is eventually enabled.
