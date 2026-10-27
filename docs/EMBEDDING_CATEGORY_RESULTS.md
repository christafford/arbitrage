# US futures category correction — 2026-10-27

The operator's first real embedding-discovery report exposed a classification bug.
US generic futures metadata was treated as a positive sports signal on every
market, excluding explicitly non-sports contracts from both generic retrieval
and embedding inference. This was not an outage of the validated 8B service.

## Diagnosis from the original archive

The bounded collection reached 20 pages per venue. Runs 20 and 21 remained
PARTIAL, retaining 4,000 records each; the broad report had 4,000 eligible Kalshi
instruments and 3,999 eligible US instruments. Original source pages remain in
`data/research.sqlite3`; the operator's report remains in
`data/first-embedding-discovery.json`.

| Captured records | Kalshi | Polymarket US |
| --- | ---: | ---: |
| Previously detected non-sports | 802 | 0 |
| Corrected non-sports classification | 802 | 557 |
| Recognized/gated sports after correction | 3,198 | 3,443 |
| Supported full-game sports identities | 2 | 0 |

These counts describe the captured records before use-time eligibility checks;
one US record was excluded by eligibility at the original ranking clock.
Of the 3,443 gated US records, four are politics/election records using the
undocumented `SPORTS_MARKET_TYPE_UNSPECIFIED` variant. They remain outside the
narrow generic-futures exception; the count is a conservative routing gate, not
a claim that those four underlying events are sports.

Previously `embedding.embedded=[512,0]` counted selected records even though no
inference took place. `status=EMPTY` occurred because there was no US input.
Final coverage and sports counts then described the empty queue, obscuring the
broad exclusions. Zero queue members did not mean zero freshly collected records.

## Implemented correction

`discovery-v3-category` treats the generic futures fields as neutral only with
an explicitly recognized non-sports category and known generic type values.
Explicit sports category/types, team metadata, game identifiers and rule-text
signals still retain sports restrictions. Unknown variants are not silently
accepted. The same correction applies to deterministic and semantic retrieval.

Diagnostics now separate `selected` and completed `embedded` counts, explain
sports exclusions and the empty-input reason, and retain the broad
`sports_coverage_at_refresh` alongside catalogue coverage. The final queue and
these diagnostics commit atomically. No schema migration, price conversion,
liquidity or settlement-approval rule changed.

Official US schema capture and hash/time are in
[the source manifest](evidence/EMBEDDING_CATEGORY_API_CHECK.json).
[Ten real catalogue excerpts](../tests/fixtures/us-category-futures-live.json)
cover eight explicit non-sports categories, an actual sports future and the
unknown election enum. Parent hashes and receipt timestamps distinguish the
reserialized excerpts from the original archived pages.

## Verification

**342 tests passed** with `python -m unittest discover -s tests -v` in the repository
virtual environment. [The log](evidence/EMBEDDING_CATEGORY_TESTS.txt) lists every test.
New tests cover real metadata and registry-envelope parsing, unknown/missing
categories/types, contradictory positive sports evidence, end-to-end hypothetical
futures retrieval, zero inference for a one-sided pool, and preservation of broad
exclusion diagnostics after an empty final queue. Existing stale/invalid-price,
liquidity, sports identity, no-approval and outage tests also passed.

The main archive is reranked using `--cached-catalogues`; no additional venue
collection is needed while the archived receipt clocks are fresh. All candidates
remain UNVERIFIED. The 20-page catalogue sample and 512-per-venue embedding cap
remain explicit limits; a nonempty shortlist is not full coverage or equivalence.


## Actual cached-catalogue recovery

The corrected CLI refresh of the existing main archive exited **0**, without
new venue requests. [Validation evidence](evidence/EMBEDDING_CATEGORY_VALIDATION.json)
records hashes of the original and rebuilt reports, source coverage, model data,
all returned suggestion identities/titles/warnings, and queue-read verification.

- Embedding status **READY**, model `qwen3-embedding-8b`, 4,096 dimensions.
- 802 Kalshi and 557 US non-sports records eligible; 512 per venue selected and
  all **1,024** inputs embedded. The semantic cap remains `truncated=true`.
- **66** successful inference-service requests (model list, probe, 64 batches);
  zero cache hits for this first real-content run. All raw responses were archived.
- **20** suggestions saved and reproduced by the separate CLI queue read, exit 0.
  Every suggestion remains UNVERIFIED, equivalence false and trading authorization false.
- All 20 suggestions have **zero deterministic heuristic score** and explicit
  conflicts. They are low-confidence thematic leads, not confirmed matching
  contracts or arbitrage opportunities. Restoring inference is not proof of useful
  opportunity coverage; the partial provider-ordered catalogue samples remain a
  material retrieval-quality limitation.

The rebuilt full report is `data/category-fixed-embedding-discovery.json`, and
its read-time queue output is `data/category-fixed-embedding-queue.json`.
The original report was preserved. Four independent offline CLI smoke commands
(demo, report, offline discovery refresh, queue) passed and are recorded in the
[smoke manifest](evidence/EMBEDDING_CATEGORY_SMOKE.json); the offline embedding
benchmark also exited 0. `git diff --check` passed.

This correction is verified. Broader/aligned catalogue coverage, meaningful
real-pair retrieval precision and human settlement review remain outstanding;
no trading, order, account or funding functionality was added.
