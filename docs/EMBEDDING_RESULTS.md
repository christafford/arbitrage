# Private embedding integration verification — 2026-10-27

Implementation, offline integration and **live Qwen3-Embedding-8B validation pass**.
The earlier reranker-output blocker below was resolved by the operator replacing
the served model. No live-money functionality or real contract approval was added.

The initial `https://cachyos.tail2be75f.ts.net/v1/embeddings` probe was reachable with
verified HTTPS. Its model listing reported `qwen3-reranker-0.6b`. A probe returned
1,024 coordinates: 14 nulls and 1,010 zeros. The client rejected that output; it
could not establish a usable embedding space or a valid model recall measurement.
That configuration required a model change; the operator subsequently supplied
the working 8B service validated below. This repository change does not alter
the gaming PC's server configuration.

## Executed validation

- **336 tests passed** with `python -m unittest discover -s tests -v` in the
  repository virtual environment; [the log](evidence/EMBEDDING_TESTS.txt) names every executed test.
- A local loopback HTTP integration exercises real request/response handling,
  batching, reordered indices, SQLite archival/cache and end-to-end retrieval.
  Production TLS remains verified; the loopback transport is test-injected.
- Tests cover environment parsing, privacy allowlisting, missing fields, invalid
  coordinates, changing dimensions/model identity, stale/future/corrupt cache,
  cache cap, HTTP failures, Retry-After, timeouts, bounded retries, persistent
  breaker recovery, partial-batch failure, raw rejection retention, migration,
  offline/read-only CLI behavior, stale metadata, coverage caps and retained
  human rejection. Existing price/liquidity/sports/registry gates run in the full suite.
- Real invalid service output is preserved in a [sanitized fixture](../tests/fixtures/embedding-invalid-live.json)
  and replayed as deterministic fallback with no cache entry or approval.

- CLI smoke commands `predarb demo`, `report`, `discovery refresh --offline`,
  `discovery queue`, `discovery refresh --cached-catalogues` (empty archive,
  unconfigured inference) and `discovery --help` all exited 0. The [smoke manifest](evidence/EMBEDDING_SMOKE.json)
  preserves exact arguments and output. The live `embeddings-check` exited 1 on
  the malformed response. `git diff --check` passed.

## Recall evidence and limits

| Run | Deterministic recall@3 | Integrated recall@3 | Interpretation |
| --- | --- | --- | --- |
| Offline hypothetical vectors | 2/6 (33.3%) | 6/6 (100%) | Tests retrieval integration only; hand-authored vectors |
| Actual configured service | 2/6 (33.3%) | 2/6 (33.3%) | Invalid probe caused deterministic fallback; **not model-quality evidence** |

[Offline report](evidence/EMBEDDING_BENCHMARK.json) and
[live attempt](evidence/EMBEDDING_LIVE_BENCHMARK.json) include per-query retrieval,
timing and status. The live benchmark exits **2**, so fallback cannot silently
count as a successful semantic benchmark. The corpus contains six hypothetical
review-relevant pairs and three unrelated distractors, with no equivalent-payout
labels. Real quality across topics and hard negatives remains unmeasured.

The initial run left live acceptance open; the subsequent 8B validation below
resolves that blocker. Full-catalogue semantic coverage and sustained production
performance are not claimed. M4/M5's previous acceptance gaps remain unchanged.

## Qwen3-Embedding-8B live acceptance

The replacement service reports `qwen3-embedding-8b`; the existing client discovers
and validates **4,096 dimensions** without a code or schema change. Configure
`PREDARB_EMBEDDING_URL=https://cachyos.tail2be75f.ts.net/v1/embeddings` (plural).
The supplied singular `/v1/embedding` spelling is not an accepted client URL;
the standard plural route was verified successfully. The singular route was not
called. The CLI probe exited 0.

[The live benchmark](evidence/EMBEDDING_8B_BENCHMARK.json) used the same six labeled
hypothetical matches and three distractors: deterministic recall@3 **2/6**, versus
embedding-assisted **6/6**. Eight candidates were returned, giving precision among
returned candidates of **6/8 (75%)**. This is actual model inference on a small
synthetic corpus, not a venue-wide quality claim or settlement evaluation.
The initial benchmark took about **12.24 seconds**, including model discovery,
probe and one 15-text batch, with the existing five-second per-socket timeout.

[Cache/queue evidence](evidence/EMBEDDING_8B_CACHE.json) shows an initial repeated
probe produced a different vector fingerprint and correctly used another cache
namespace. A subsequent repeat reused that fingerprint, hit **15/15 cached texts**,
made only two requests (model listing and probe), and took about **1.54 seconds**.
Probe variation can conservatively reduce cache hits; no tolerance was introduced
to silently combine model spaces. Queue rereads reproduced the saved candidates;
all remained UNVERIFIED, trading authorization false, and the pair registry empty.

[The live fixture](../tests/fixtures/embedding-8b-live.json) preserves the exact probe,
a sanitized model-list excerpt and the first two vectors excerpted from the real
15-text batch. Representations, UTC receipts, hashes and parent hashes are explicit;
original responses were archived before conversion in `data/embedding-8b-check.sqlite3`.
Its inputs are labeled hypothetical. The added offline regression replays model
and dimensions discovery, batch validation and cache reuse without network access.
All **337 tests passed** with `python -m unittest discover -s tests -v`; the
[post-change log](evidence/EMBEDDING_8B_TESTS.txt) lists every executed test.
[CLI smoke evidence](evidence/EMBEDDING_8B_SMOKE.json) records exit 0 for the real
model probe, demo/report, offline refresh and queue. The offline commands ran
with the embedding URL set and still made no inference calls.

Live model/dimension and small-corpus benchmark acceptance are now satisfied.
No timer was enabled, production archive migrated, or persistent service
environment changed by these checks. Existing fresh-catalogue eligibility and
human approval gates still apply.
