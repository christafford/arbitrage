# M5O — Kalshi omitted bid-ladder correction

**The repeated missing-ladder failures were a parser bug, and the correction is
implemented.** Kalshi's official WebSocket snapshot schema explicitly permits an
omitted YES or NO ladder when that side has no orders. Our parser incorrectly
required both arrays. This is a known empty side, not an unknown price or quantity.

Four exact archived snapshots reproduce the problem:

| Pair | Archived snapshot UTC | Omitted side |
| --- | --- | --- |
| Brooklyn–Indiana | Nov 2 00:41:53.649281 | NO |
| Boston–Orlando | Nov 1 22:55:44.494849 | NO |
| Arizona–Dallas | Nov 1 21:39:33.720547 | NO |
| Baltimore–Buffalo | Nov 1 20:51:11.880798 | YES |

The previous parser raised a schema exception, invalidated the book and retried
the connection. Repeated partial snapshots eventually triggered M5O's consecutive
failure limit. The corrected parser preserves stream continuity while marking
these snapshots `PARTIAL_BOOK`, or `EMPTY_BOOK` if both sides are absent. Both
remain `data_usable=false`; neither can authorize conditional or strict economics.

Full snapshots still replace the whole book: omission clears old depth instead
of carrying it forward. Valid sequenced deltas can populate an empty side later.
Present null/non-list values, malformed levels, off-grid/invalid prices and
quantities, missing identity/clock fields, sequence gaps and stale data still
reject. REST normalization, settlement, fee and collateral gates are unchanged.

## Observed verification and limits

All four genuine historical snapshots now parse as partial, unusable books in
explicit **counterfactual parser replay**. Original raw bytes and their persisted
`REJECTED` status remain untouched; normal archive inspection still rejects them.
The fixture includes exact public-frame/metadata hashes, adapter schema versions,
original receipts and the current official-document receipt.

A separate 15-second capture on the open December Fed 25-bps-cut market recorded
six valid raw responses, including **two snapshots with omitted YES ladders**.
Both replay as `PARTIAL_BOOK`, with zero missing-ladder/schema failures. The feed
was quiet: two unchanged-policy `MESSAGE_TIMEOUT` events occurred, no deltas were
observed, and the capture correctly reports **INCOMPLETE**. This proves live
schema handling, not economic eligibility or sustained continuity.

An initial Brooklyn live probe could not demonstrate this correction because the
market had finalized; its three rejected stream responses remain preserved as a
separate failed probe. Fresh public detail checks around **Nov 2 02:38 UTC** show
that **all four stopped sports markets are now finalized**. Restarting those
subscriptions would not restore an open-market observation window.

Tests cover omitted YES/NO/both sides, replacement clearing, sequenced recovery,
malformed present values, missing required fields, stale/invalid data, raw-first
capture, historical rejection preservation and the four genuine examples. The
full test output is [recorded here](evidence/M5O_LADDER_FIX_TESTS.txt); exact counts
and executed smoke commands are in [the verification manifest](evidence/M5O_LADDER_FIX.json).

## Active-run boundary

The correction is available for newly started processes. The ongoing M5O service
and its remaining workers were **not restarted or hot-patched**; they retain the
original code loaded at launch, which is saved under the run's `code/` directory.
The original deadline remains **Nov 2 19:43:05 UTC / 14:43:05 EST**. Historical
captures and failure gaps are preserved, and no run was renewed. The live probes
use separate archives under `data/m5o/ladder-investigation/` and are not counted
toward the 24-hour comparison's coverage or opportunity totals.
