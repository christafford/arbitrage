# M5I proposition compatibility and error evaluation — October 31

**The four observed mismatch patterns are repaired; broad production quality is
still unproven.** Versioned v3 guards add explicit ranges, geography, event kind,
named departure subjects/countries and announcement-versus-actual-departure rules.
A zero-score tie fix also prevents some relevant candidates from losing event
diversity selection to more contradictory candidates. All warnings, approvals,
source freshness, horizon, fees and collateral gates remain intact. No backfill
or inference service was started.

## Implementation and limits

- Ranges preserve Decimal endpoints, explicit units and unknown inclusivity.
  `between 0.1% and 0.5%` is different from `above 2.2%`; overlapping ranges are
  not identical outcomes either. `between` alone never implies inclusive endpoints.
  Missing/mixed units, reversed or multiple ranges, and ambiguous magnitudes stay
  unknown. Current range-versus-threshold comparison supports a single one-sided
  threshold; compound constraint algebra is not implemented.
- Geography recognizes explicit US national versus California gas-price wording,
  and global versus US Spotify charts. This is not a general geography resolver.
- Event kinds distinguish recognized GDP growth, gas-price, Spotify streaming
  rank, Grammy award and presidential-departure assertions. Unrecognized or mixed
  kinds stay unknown; the parser is not an exhaustive event taxonomy.
- Named subjects and countries are extracted only from narrow presidential
  departure assertion grammars. Compound/generic names stay unknown. General
  aliases, transliterations, organizations and other political offices remain
  outside this parser; exact-name differences still need human review.
- Explicit announcement/announced-intention rules stay distinct from actually
  leaving office, even when the named person and office match.
- The persistent retriever breaks equal-score ties by fewer explicit conflicts,
  before liquidity and cosine. Conflict status and score still take precedence.
  This avoids arbitrary source-ID selection among zero-score candidates without
  calling any contradictory candidate equivalent. Event diversity remains bounded.

The checks apply on read to old features and saved candidates. Original public
text/content hashes, cached vectors, model namespaces and database schemas are
unchanged. Previously saved JSON reports remain historical; queue reads/retrieval
recompute current guards.

## Genuine development corpus

[The fixture](../tests/fixtures/m5i-compatibility-genuine.json) contains **60 genuine
archived definitions and 42 labeled pairs**, assessed at the preserved clock
`2026-10-31T11:59:30.514822+00:00`. Each definition retains source URL, schema,
receipt time, original version, parent raw hash and excerpt hash. Parent raw bytes
were verified before export, and the evaluator validates each excerpt through the
existing official venue adapters. [Current official document receipts](evidence/M5I_COMPATIBILITY_API_CHECKS.json)
cover the existing consumed text fields; no API fields or endpoints were added.

Labels have two independent meanings:

1. **Retrieval relevance:** the same ordinary event/outcome is worth examining.
   There are 19 relevant pairs and 23 irrelevant pairs.
2. **Expected proposition/rule conflict:** explicit differences must be flagged.
   There are 24 such pairs, including four inverse sports selections. A same-person
   departure pair is retrieval-relevant but has incompatible announcement/actual
   rules; relevant does not mean settlement-compatible.

These are **assistant labels**, not operator adjudications. This purposive
regression/development corpus is not held out or representative. Unlisted cross
pairs are **UNLABELED**, never silently counted as negatives. All candidates remain
UNVERIFIED. The two frozen baseline modules come byte-for-byte from commit
`ced3d33`; current and baseline code/data hashes are recorded in the results.

## Measured false positives and false negatives

[Complete per-pair/per-query results](evidence/M5I_COMPATIBILITY_EVALUATION.json)
include three offline variants on the same genuine corpus. The original
non-indexed deterministic retriever uses frozen v2 guards; the indexed comparator
freezes both v2 guards and the preceding retrieval implementation. The new variant
uses v3 guards and the conflict-count tie fix. No vectors or inference are used
in this controlled comparison; this is not a model-quality benchmark.

| Measure | Prior deterministic | Prior indexed v2 | Updated indexed v3 |
| --- | ---: | ---: | ---: |
| Relevant pairs at Recall@20 | 19/19 | 16/19 | **18/19** |
| Relevant pairs at Recall@100 | 19/19 | 16/19 | **18/19** |
| Labeled unflagged false positives | 7 | 5 | **0** |
| Labeled unflagged precision | 9/16 (56.25%) | 7/12 (58.33%) | **8/8 (100%)** |
| Unlabeled unflagged returns, excluded from precision | 7 | 2 | 0 |

Precision is conditional on labeled, unflagged returns within the actual top-k;
filtering does not refill the queue. Raw recall includes relevant pairs carrying
material warnings, and unflagged does not imply approval. Equal @20/@100 values
reflect the small candidate pool and event diversity, not proven production-scale
recall. The prior deterministic retriever still has higher raw recall here; the
updated indexed retriever retains the pre-existing horizon exclusion.

For the **34 non-sports pair labels**, the proposition parser alone detects
**20/20 expected conflicts**, versus **11/20 before**. Missed conflicts fall
**9 → 0**. Both versions flag **0/14 compatible ordinary-proposition controls**
incorrectly. Four inverse sports pairs remain rejected by the established sports
identity gate and are excluded from this parser-only denominator.

The complete comparison path still warns on **10 ordinary-proposition controls**:
eight CPI pairs, one nomination pair and one national gas-price pair. These carry
existing resolution-language/date warnings. They are recorded separately from
parser false positives: assistant ordinary-event labels do not establish that
these legal/settlement warnings are erroneous, and no warning was removed to
improve a metric.

## Retrieval misses and what changed

- **US Spotify top song:** v2 could retain the global chart counterpart instead.
  Explicit geography now selects the US counterpart for the US query.
- **National gas below $3.20:** several candidates had score zero. The old source-ID
  tie selected a different threshold/direction. The conflict-count tie selects the
  national $3.20 candidate while preserving its date/resolution-language warnings.
- **Zelenskyy departure:** still absent from indexed results. The administrative
  settlement horizons differ by **187.5 days**, exceeding the existing 90-day
  retrieval filter. The parser now also flags announcement/intention versus actual
  departure. This miss is reported, not fixed by weakening the filter or pretending
  the contracts are equivalent.

Thus indexed retrieval misses fall **3 → 1**, with the remaining category
`same_event_different_rule` and stage `SETTLEMENT_HORIZON_FILTER` explicitly recorded.
No new production reviewable-event yield or venue-wide precision is inferred.

## Production replay and validation

The saved October 31 production queue was re-ranked read-only at its original
clock. **Four of 100 rows gained explicit conflict flags**: GDP range/threshold,
California/national gas, Spotify/Grammy criterion, and Fujimori/Zelenskyy departure.
[Replay with original and updated warnings](evidence/M5I_COMPATIBILITY_QUEUE_REPLAY.json).
The other generic rows are not thereby certified correct; broader entity and
proposition recognition remains incomplete. No production source/index write or
reembedding was needed.

The earlier 49-definition corpus still retrieves **18/18 positives at @20/@100**
in historical deterministic replay, with 11 distinct events and zero additional
labeled events versus its deterministic comparator. Its older closed-world label
assumption differs from this new explicit-unlabeled evaluation; do not combine
precision denominators across them.

Reproduce offline:

```bash
.venv/bin/python scripts/m5i_compatibility_evaluate.py \
  --directory data/new-compatibility-evaluation \
  --output data/new-compatibility-evaluation.json
.venv/bin/python -m unittest discover -s tests -v
```

The evaluation directory must be new. It bounds the corpus at 500 definitions and
500 pairs, rejects missing/duplicate/non-boolean labels, hash failures and stale or
ineligible definitions, and never writes approvals or calls the network. Results
retain all labeled pair warnings, unlabeled counts and false-negative categories.
**409 tests passed in 18.948 seconds** with the full command above;
[exact output](evidence/M5I_COMPATIBILITY_TESTS.txt). Tests include parser ambiguity,
unknown units/inclusivity, genuine positive/negative controls, perfect-cosine
stress, zero-score diversity, stale/corrupt corpus rejection, label accounting
and restoration of baseline contexts after errors. `pip check` passed.
[Code/fixture hashes, original-corpus replay and service status](evidence/M5I_COMPATIBILITY_MANIFEST.json)
are retained.

Remaining work: independent operator adjudication, a broader held-out corpus,
range/entity/event parsing outside the documented grammars, final-catalogue
retrieval coverage, and sustained semantic yield. The backfill services remain
stopped and disabled. Stop after M5I; no M6 or trading work is authorized.
