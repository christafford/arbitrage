# Private embedding integration verification — 2026-10-27

Implementation and offline integration pass. **Live semantic acceptance is blocked
by invalid output from the configured service.** No live-money functionality or
real contract approval was added.

The supplied `https://cachyos.tail2be75f.ts.net/v1/embeddings` URL is reachable with
verified HTTPS. Its model listing reports `qwen3-reranker-0.6b`. A probe returned
1,024 coordinates: 14 nulls and 1,010 zeros. The client rejects this output; it
cannot establish a usable embedding space or a valid model recall measurement.
Configure the service to return finite, nonzero embedding vectors, then rerun
`discovery embeddings-check` and the `--live` benchmark in [the guide](EMBEDDINGS.md).
This repository change does not alter the gaming PC's server configuration.

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

The active milestone remains open for valid service output and successful live
model benchmarking. Full-catalogue semantic coverage and sustained production
performance are not claimed. M4/M5's previous acceptance gaps remain unchanged.
