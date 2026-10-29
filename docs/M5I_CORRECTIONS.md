# M5I contradiction corrections and inference diagnosis — October 29

**The four observed contradiction misses are fixed and tested. The operator has
restored inference; HTTP health now passes, but the exact model pin does not.**
Both expired run services remain disabled. No bulk backfill, new model namespace,
real-money workflow or equivalence approval was started.

## Retrieval changes

`propositions.py` extracts explicit assertions from existing verified public rule,
description and selected-outcome fields. It compares Decimal amounts, magnitude
suffixes, inequalities, observation periods, recognized proposition types and
displayed-bucket rounding. A definition's first settlement assertion takes
precedence over generic question text; titles/subtitles provide a fallback when
the assertion has no recognized threshold. Later rule text remains available for
rounding-policy detection.

Absent units and unrecognized language stay unknown. In the Bitcoin case, the US
public wording has no explicit currency symbol; it is not silently converted to
USD. Opposite inequalities and window-versus-instant definitions independently
establish the reported conflicts.

| Genuine archived candidate | New material flags |
| --- | --- |
| December Fed 25-basis-point hike | `ROUNDING_CONFLICT` |
| Musk $1.7 trillion / $1.2 trillion | `PROPOSITION_THRESHOLD_CONFLICT` |
| Supreme Court confirmation count / next appointee | `PROPOSITION_TYPE_CONFLICT` |
| Bitcoin window high / final-time low | `PROPOSITION_DIRECTION_CONFLICT`, `OBSERVATION_WINDOW_CONFLICT` |
| Spotify “Stateside” | No new conflict detected; still requires operator review |

Both deterministic and persistent semantic retrieval rank material contradictions
after candidates without detected contradictions, before similarity or liquidity
tie-breakers. Tests supply a **hypothetical cosine of 1** to all four negative
cases; conflicts remain authoritative. A dirty candidate's high score cannot
raise the deterministic pruning floor and hide a lower-scoring clean candidate.

Existing sidecar rows and saved reservoirs recompute versioned guards from their
bounded public text at comparison time. Main queue reads recompute comparisons
from current source versions. An old empty `known_contradictions` list therefore
does not survive simply because its rule version is unchanged. The parse cache
holds at most 512 public texts, each bounded at 16,000 bytes. No schema migration,
embedding-text change or vector rebuild is required; model namespaces are preserved.

This is a partial language parser, not proof of identical contracts. Unknown
clauses, unrecognized phrasing, exceptional settlement and account applicability
still require human review. Broader M5I coverage and quality gaps remain open.

## Measured regression evidence

- **387 tests passed** with `python -m unittest discover -s tests -v` in 17.125
  seconds. Ten new tests cover the genuine misses, magnitude/inequality variants,
  missing units/schema/text, observation periods, old sidecar features/main queues,
  deterministic ordering, stale evidence and changed source versions.
- The [genuine fixture](../tests/fixtures/m5i-contradictions-genuine.json) contains
  ten archived definitions for the five pairs. Adapter schemas, parent/excerpt
  hashes, URLs, receipt clocks and original version references are preserved.
  Labels are assistant assessments, not independent adjudication or approvals.
- Read-only replay of the saved **100-event queue** at its original 13:25 UTC clock
  newly flagged **exactly the four reviewed misses**, with no inference or database
  write. Existing vector checksums and source versions were validated.
  [Before/after scores and warnings](evidence/M5I_CORRECTION_REPLAY.json) retain
  actual archived cosine provenance. All candidates remain `UNVERIFIED`.
- The prior 49-definition genuine corpus still finds **18/18** labeled propositions
  at Recall@20 and Recall@100, with 18/18 precision among returned persistent-index
  candidates in deterministic historical replay. No new inference ran and no new
  reviewable event/model-quality gain is claimed. Both comparator implementations
  use updated code; this regression is not a new old-versus-new ablation.
- CLI replay/help and dependency checks passed. Exact test output, commands,
  fixture hashes and corpus metrics are in the
  [validation manifest](evidence/M5I_CORRECTION_VALIDATION.json).

Reproduce the queue regression without network requests:

```bash
.venv/bin/python scripts/m5i_replay_contradictions.py \
  --db data/research.sqlite3 --index-db data/m5i/index.sqlite3 \
  --snapshot docs/evidence/M5I_RUN_20261028_FINAL_QUEUE.json \
  --output data/m5i-replayed-queue.json
```

Replay fails if required source versions or archived vectors are no longer
available. Use preserved archives for a later historical replay.

## Private inference diagnosis

At 20:02 UTC, the PC responded directly to Tailscale ping (102 ms), and the private
HTTPS `/v1/models` route returned **HTTP 502 three times** with empty bodies. At
20:14 UTC, `/health` also returned 502. Exact responses are archived in
`data/m5i/corrections-20261029/diagnostics.sqlite3`; hashes and clocks are in
[the diagnosis manifest](evidence/M5I_CORRECTION_DIAGNOSIS.json).

These requests fail before market text reaches embedding inference. A
front-end/upstream failure is a working hypothesis; a model crash, OOM, wrong
forward target or stopped local service cannot be distinguished from these
responses alone. Documented llama.cpp health responses are 200 when ready and
503 during loading; the empty 502 is not evidence of a normal loading response.
[Official llama.cpp documentation](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md#api-endpoints).

OpenSSH and the Tailscale SSH wrapper both failed host-key verification. No host
verification, credentials, firewall or Serve configuration was changed. The
operator was asked for a verified SSH connection/fingerprint or PC-side status
output; that information is needed to finish the repair.

On the PC, inspect `tailscale serve status`, identify its actual local upstream,
and check that upstream's `/health`, service status and logs. Do not assume a
port from examples or start a competing model process. Restore the existing
service after identifying its failure, then verify the exact model fingerprint
with a small bounded embedding batch. Keep the listener private; Tailscale Serve
supports a local service without public Funnel exposure.
[Official Serve documentation](https://tailscale.com/docs/features/tailscale-serve).

Official diagnostic docs and current US market-field schemas were captured with
UTC timestamps and hashes. No new exchange API fields are consumed. Bulk backfill
remains stopped until inference health, the model pin and a bounded batch pass.

## Recovery check — October 29, 22:46 UTC

The operator reported accidentally closing the server and restarting it. The
private `/health` endpoint returned HTTP 200 with `status=ok`. Three actual
embedding probes returned valid 4,096-dimensional `qwen3-embedding-8b` vectors,
but none matched the existing `6ad290cf…` namespace. The first fingerprint was
`1bdbff0b…`; the next two both returned `8f1b7456…`. Their cosine similarity to
the archived pinned probe was approximately 0.99985 and 0.99983 respectively.
High similarity does not establish cache compatibility or authorize merging.

The bounded worker requested at most 64 Kalshi / 16 US definitions, 60 seconds,
and eight texts/second. It exited 2 (`PINNED_MODEL_IDENTITY_MISMATCH`) after six
HTTP requests and 3.056 seconds, before embedding any market text. Zero market
vectors were added; the active namespace remains the original pin. The expired
services remain disabled and their deadline/checkpoints were not modified.
[Health, exact fingerprints, source references and validation](evidence/M5I_RECOVERY_20261029.json).

The operator supplied a launch script naming `Qwen3-Embedding-8B-Q6_K.gguf`,
last-token pooling, loopback host, port default 8083, GPU layers `auto`, fit `on`,
768 MiB fit margin, flash attention on, context/batch 2048, microbatch 256,
parallelism 1 and six threads. Effective runtime parameters, GGUF checksum and
llama.cpp build are not yet verified. No prior effective launch manifest was
found in repository documentation. Automatic GPU placement is a diagnostic lead,
not an established cause: the official help describes automatic GPU layers and
memory-fitting adjustments. Capture the actual offloaded-layer/backend startup
lines, build version and model SHA-256 before attempting runtime restoration.
[Official llama.cpp parameter documentation](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md).

No matching guard or model pin was relaxed. Full tests were rerun: **387 passed
in 19.048 seconds**; `pip check` reported no broken requirements. This is recovery
diagnosis, not completed backfill or a new retrieval-quality result.

### Operator runtime evidence and cache diagnostic — 23:11 UTC

The operator supplied SHA-256
`25e215d4283e3a48ca65a622b70a357599fd480282f48a3ecd6e3e8828d92a66`
for the GGUF and build 10705 / commit `3f5abc5`. A private GET `/props` independently
reported `b10705-3f5abc5`, the expected local model path, one slot and context 2048.
The old/current `/v1/models` metadata agrees on Q6_K, dimensions, parameter count,
model size and context. The original GGUF checksum was not captured; matching
metadata cannot establish identical model bytes or effective runtime.

The supplied log explicitly reduces logical batch 2048 to microbatch 256 and
shows repeated nine-token probes reusing eight cached tokens. It does not show
GPU/backend or offloaded-layer counts. A six-request isolated diagnostic (one
model request and five embedding requests) returned `8f1b7456…` throughout,
including three requests carrying `cache_prompt=false`. No restoration of the
old pin occurred. The embedding route may ignore this field; no claim that prompt
reuse was actually disabled follows from HTTP success. Raw requests/results and
properties provenance are added to the recovery evidence. Production source/index,
worker settings, services and pin were unchanged in this follow-up.

The next diagnostic is a startup capture with trace logging (`-lv 4`) to expose
actual backend/offload settings, retaining all existing inference arguments.
Current upstream documentation identifies level 4 as trace; it is not evidence
that the running build has identical internals. The exact supplied commit could
not be retrieved through the web tool. Backfill remains stopped. This follow-up
changed only documentation/evidence. The full suite was nevertheless rerun:
387 tests passed in 18.012 seconds; exact output is retained locally at
`data/m5i/recovery-20261029/cache-diagnostic-tests.txt`.

### Full trace and isolated batch — 23:14–23:16 UTC

The operator's trace confirms Vulkan on an RTX 3080, all 37/37 layers offloaded,
flash attention enabled, f16 KV, context 2048, batch/microbatch 256 and one slot.
The fitting step explicitly made no adjustment: projected GPU use 6366 MiB versus
7944 MiB free left 1578 MiB, above the requested 768 MiB margin. This eliminates
partial offload as an explanation for this particular startup; the original
run's effective placement is not known. A bounded production-pin retry still
returned `PINNED_MODEL_IDENTITY_MISMATCH` after six requests and 3.522 seconds,
adding zero market vectors.

An isolated archive (`data/m5i/recovery-20261029/runtime-validation.sqlite3`)
then embedded all ten hash-checked genuine definitions from the correction
fixture. All returned valid 4096-dimensional vectors. Seven HTTP requests,
including before/after probes, took 6.677 seconds. This is a protocol/runtime
check on archived text, not a live eligibility or retrieval-quality result.
Production vectors and the active pin were not changed by the isolated check.

The probe before the batch returned `8f1b7456…`; the first probe after the batch
returned `1bdbff0b…`, and its repetition returned `8f1b7456…`. This demonstrates
request-history-dependent exact fingerprints within one running server. It does
not establish compatibility with the older `6ad290cf…` vectors. The existing
three-probe pin gate remains unchanged; no numerical tolerance or identity merge
was introduced.

The operator was offered a separately pinned namespace for the current verified
runtime, retaining original vectors and checkpoints. This entails re-embedding
previously indexed definitions for the new namespace, not deleting or recollecting
all archived market data. Direction is pending because AGENTS explicitly requires
preserving the existing pin. No new sustained run has started; there is no new
check-back deadline.

The full suite was rerun: **387 tests passed in 17.523 seconds**. Exact local
output is recorded in the recovery evidence. No application code changed.
