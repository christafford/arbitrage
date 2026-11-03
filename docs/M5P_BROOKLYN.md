# Brooklyn observation reconstruction

The single positive M5O observation at **2026-11-01 22:47:03.884165 UTC** is
supported by the raw messages visible to its historical reader. Reconstructing
the original Kalshi snapshot/delta chain and US full snapshot reproduces its
quality checks and Decimal gross-price calculations exactly. This is one valid
timestamp/depth observation, not proof of persistence, fills, net profit or
settlement equivalence.

Archive: `data/m5o/run-20261101/nba-brooklyn/segment-012/`. The full reconstruction,
all price levels, quantities, raw pointers and hashes are in
[M5P_HISTORY.json](evidence/M5P_HISTORY.json). The self-contained genuine
[fixture](../tests/fixtures/m5p-brooklyn-live.json) includes the raw generations,
metadata and three US responses; its unit test rebuilds the books offline.
The forensic routine additionally replays original committed-reader frontiers.

| Sample UTC | Kalshi NO best / quantity | US YES best / quantity | Source skew | Quality |
| --- | --- | --- | ---: | --- |
| 22:46:58.559147 | $0.55 / 30,144.49 | $0.44 / 70,518.85 | 25.543216 s | Rejected: stale US source and source skew |
| 22:47:03.884165 | $0.55 / 30,644.49 | $0.44 / 53,237.71 | 0.787165 s | Pass at this sample |
| 22:47:08.246378 | $0.55 / 33,311.49 | $0.44 / 53,237.71 | 5.065165 s | Rejected: stale US source and source skew |

At the positive sample, Kalshi source send time is **22:47:03.727000**, receipt
**22:47:03.752282**. US source `transactTime` is
**22:47:02.939835179**, receipt **22:47:03.873174**. The respective source ages
are 0.157165 and 0.944330 seconds (microsecond comparison precision); receipt
skew is 0.120892 seconds. Original nanosecond US strings remain preserved.

Kalshi selected raw ID **22510** has SHA-256
`3e8c497df63cd914da51fde83cd355c1dc28d4bfc26828ffbf15057f7f62ec39`.
US selected raw ID **332** has SHA-256
`a45d5c3206ffe7c23e9cdcf35d9934a6802443a79592f6e0335760c57bea5b18`.
The next US polling response, ID 334, is byte-identical to ID 332 and retains the
same source time. It was not promoted into a second passing observation.

The immediate Kalshi raw neighbors also reconstruct successfully:

| Raw ID | Source send UTC | Receipt UTC | Best NO / quantity |
| --- | --- | --- | --- |
| 22509 | 22:47:03.593000 | 22:47:03.627414 | $0.55 / 30,644.49 |
| 22510 | 22:47:03.727000 | 22:47:03.752282 | $0.55 / 30,644.49 |
| 22511 | 22:47:04.137000 | 22:47:04.162118 | $0.55 / 30,644.49 |

These neighbors establish the observed Kalshi depth around the sample, not
continuous cross-venue state validity. US REST has no intervening-delivery
guarantee, and the five-second samples cannot establish continuous duration.

The selected legs cost **$0.99 per matched unit before fees**, conditional on
ordinary outcomes paying $1 in total. That is a $0.01 gross discrepancy per unit,
or approximately 1.0101% of quote cost. The $100 quote budget admits 101.01 units,
costing $99.9999 with $1.0101 gross indicative gain. The $500 case admits 505.05
units, costs $499.9995 and has $5.0505 gross indicative gain. Both fit the displayed
best-level quantities. Unknown fees, collateral, cash release and exceptional
settlement outcomes remain unresolved; no profit or fill occurred in this study.

All three original statuses are preserved. There is one positive sample, one
sample cluster and **zero measured cluster span**. Repeated price levels on stale
snapshots cannot support a persistence claim.
