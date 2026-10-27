# Private embedding retrieval

This discovery extension adds review candidates using the private llama.cpp service.
Every suggestion remains `UNVERIFIED`, `equivalence_verified=false` and
`trading_authorized=false`. Human decisions, money calculations and execution
permissions are independent. Embeddings cannot approve contracts or trades.

## Setup and verification

Back up an existing archive with `predarb ops backup` before upgrading. Opening a
writer migrates SQLite 7 to 8 atomically, adding a derived cache and persistent
circuit-breaker table. Existing source evidence and reviews are preserved. Use the
repository virtual environment and updated package on the Florida server.

```bash
. .venv/bin/activate
export PREDARB_EMBEDDING_URL='https://cachyos.tail2be75f.ts.net/v1/embeddings'
predarb discovery embeddings-check --db data/research.sqlite3
predarb discovery refresh --cached-catalogues --db data/research.sqlite3 --limit 100
predarb discovery queue --db data/research.sqlite3 --limit 20
```

The current service has been validated as `qwen3-embedding-8b` with 4,096 dimensions
and a successful small-corpus live benchmark. Use the plural `/v1/embeddings` URL.
See [the acceptance results and limitations](EMBEDDING_RESULTS.md).

The check prints the served model ID, cache identity and measured vector dimension;
it archives the model response and probe response. It does not assume a dimension
from a model name or GGUF metadata. The service must expose both `GET /v1/models`
(exactly one model) and `POST /v1/embeddings`. Enable embedding pooling on llama.cpp.
The URL accepts an HTTPS origin, `/v1`, or `/v1/embeddings`; custom ports, userinfo,
queries, fragments and other paths are rejected. TLS certificate verification is
mandatory. Environment proxy settings and redirects are disabled. No API key is
needed or read. Use Tailscale ACLs to restrict access to the private service.

`refresh` with the variable set collects public catalogues normally and adds
embedding retrieval. `--cached-catalogues` skips venue requests and embeds only
currently eligible archived instruments; it cannot renew stale metadata.
`--offline` always uses the deterministic matcher without any network requests,
even when the URL is set. `queue` and `pairs candidates` also make no inference
requests. Queue reads retain previously saved semantic suggestions only while
both rule versions and existing catalogue eligibility checks still hold.
`--sports-only` retains the existing NBA/NFL matcher and skips embeddings.

For the existing discovery systemd timer, add a service drop-in with
`Environment="PREDARB_EMBEDDING_URL=https://cachyos.tail2be75f.ts.net/v1/embeddings"`.
The interactive shell environment is not automatically inherited by systemd.
The code change does not install, enable or restart services.

## Data boundary and caching

Only allowlisted public title, question, subtitle, YES subtitle, description,
rules and cutoff text is sent. Full instrument metadata, imported human review
forms, account state, credential files, environment values and trading headers
are never serialized into inference requests. Market text is bounded to 16,000
UTF-8 bytes; oversized content triggers explicit deterministic fallback, without
silently truncating rules. These are inference POSTs, not exchange writes.

Cache keys combine SHA-256 of the exact versioned public text with model identity.
Identity covers the endpoint, served model ID, local protocol/text versions and a
fixed probe vector fingerprint. Probe fingerprint changes isolate same-name model
replacements conservatively; numerical nondeterminism can cause cache misses.
Use an immutable GGUF/version alias on the server. The API does not supply a
cryptographic hash of model weights, and a change immediately after probing cannot
be detected if the server reuses an ID and dimensions. Keep the model fixed during
a discovery run. Response model mismatch or dimension drift rejects the entire
semantic contribution for that run.

Cache TTL is 30 days, with a 20,000-row newest-first cap. Changed content, identity,
expired/future timestamps or invalid cached vectors require new inference. Each
cached vector records dimensions, UTC receipt time and raw response reference.
Raw model/embedding responses commit before JSON/schema validation, including
HTTP errors. They use `llama-embeddings/v1`, retain original bytes and SHA-256,
and contain no request authentication. Raw evidence is retained like existing
venue evidence; it is not pruned with the derived cache. Monitor archive growth.

## Bounds and failure behavior

Defaults are five-second socket timeouts, at most two retries after the first
attempt, exponential waits of one and two seconds, 16 texts per batch, 100 total
HTTP attempts per client, 4 MiB per response and at most 8,192 vector coordinates.
Retry-After is honored; waits over eight seconds open the circuit rather than
blocking the matcher. Transport failures and exhausted retryable HTTP errors
open a persistent circuit for at least 60 seconds. A later request after cooldown
is a recovery probe; success clears the circuit. Schema failures open the circuit
without retrying unknown data. Errors are sanitized before reporting.

Only the first 512 eligible non-sports instruments per venue (stable source-ID
order) receive embeddings per refresh. Coverage reports this cap as `truncated`; `selected` counts planned inputs and
`embedded` counts completed inputs. `non_sports_eligible` and `excluded_sports`
explain filtering. A one-sided selection produces EMPTY and zero completed inputs;
the deterministic matcher still searches its full eligible scope. Retrieval uses
bounded brute-force cosine similarity, five neighbours per Kalshi instrument and
a 0.75 minimum similarity. These are retrieval heuristics, not probabilities.
Float math is confined to vectors; prices, quantities and profits retain exact
arithmetic. Large-dimension CPU retrieval needs real-host timing before increasing
these caps; this implementation does not claim full-catalogue semantic coverage.

Semantic neighbours supplement lexical retrieval, while deterministic scores,
date/threshold conflicts, unsupported sports exclusions and liquidity checks
remain in force. Conflicts can enter the human review queue with warnings;
similarity never removes a warning or overrides a rejection. Missing, stale,
invalid or partial book liquidity cannot become an executable quantity.

On a network, schema, input or I/O failure, the report has
`embedding.status=FALLBACK` with a reason and computes the deterministic candidates.
Partial inference results are not mixed into that refresh. Successfully cached
batches can be reused after recovery. An unset variable reports `DISABLED`.
A malformed configured URL is a configuration error; fix/unset it or use
`--offline`. A successful CLI exit alone does not imply embedding availability;
inspect the `embedding` object and venue coverage.

## Reproducible recall benchmark

```bash
python scripts/embedding_benchmark.py --output data/embedding-offline.json
PREDARB_EMBEDDING_URL='https://cachyos.tail2be75f.ts.net/v1/embeddings' \
  python scripts/embedding_benchmark.py --live --output data/embedding-live.json
python -m unittest discover -s tests -v
```

The benchmark uses an isolated temporary database, six hand-labeled hypothetical
review-relevant pairs and three unrelated distractors. It reports per-query
recall@3, precision among returned candidates, elapsed time, coverage and model
identity for the existing matcher and integrated matcher, using identical data.
Offline vectors are hand-authored solely to test integration; their recall is
not model-performance evidence. `--live` calls the actual service with the same
hypothetical text and exits 2 on fallback. Neither mode is a representative
venue-wide quality study or settlement-equivalence evaluation. Expand the labeled
corpus and include hard negatives before tuning deployment retrieval parameters.

See [verification results](EMBEDDING_RESULTS.md), [source contract](API_SOURCES.md)
and [raw benchmark output](evidence/EMBEDDING_BENCHMARK.json).


US generic futures metadata is interpreted with the explicit market category;
non-sports futures are eligible for embedding retrieval. Unknown types and
recognized sports retain conservative gates. See the [category correction](EMBEDDING_CATEGORY_RESULTS.md)
for the initially empty real-catalogue run and its recovery.
