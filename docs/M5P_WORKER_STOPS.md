# Five M5O early worker stops

All five stops are explained. In each final segment, a Kalshi snapshot omitted an
empty side while the launch-time parser required both ladders. Snapshot rejection
invalidated stream provenance, reconnects repeated the schema failure, and the
worker reached its 12-consecutive-book-error limit. This was a parser/worker
failure mode, not evidence of a profitable or tradable empty book.

| Worker | Final segment rejected snapshots | Omitted side | Worker stopped UTC | Later reported trading close UTC |
| --- | ---: | --- | --- | --- |
| Brooklyn | 8 | NO | Nov 2 00:42:18.751434 | Nov 2 00:47:46 |
| Boston | 5 | NO | Nov 1 22:56:09.088937 | Nov 1 23:03:46 |
| Toronto | 5 | YES | Nov 2 04:18:02.478732 | Nov 2 04:31:51 |
| Arizona | 5 | NO | Nov 1 21:40:00.837174 | Nov 1 21:41:24 |
| Baltimore | 5 | YES | Nov 1 20:51:37.977011 | Nov 1 21:25:26 |

The last metadata archived in every final segment still reports **active**.
All 28 rejected final-segment frames are snapshots with an omitted ladder. Each
worker's final 12 samples reports the same stream-provenance inspection error.
Exact raw IDs, hashes, times and terminal error lists are in
[M5P_HISTORY.json](evidence/M5P_HISTORY.json). A fresh public detail capture on
November 3 confirms all five are now finalized and records their close times in
[M5P_FINALIZATION.json](evidence/M5P_FINALIZATION.json).

The worker stops precede those later reported closes. We therefore attribute the
initial stops to the parser/failure-limit chain, not to finalization. Finalization
subsequently made a restart inappropriate; it cannot justify ignoring the earlier
observation gaps. The exact time of the venue's internal finalization transition
was not continuously observed.

The [existing ladder correction](M5O_LADDER_FIX.md) remains intact. Its four
genuine examples still pass counterfactual parser tests and remain unusable
`PARTIAL_BOOK` states. M5P adds a fifth genuine
[Toronto regression fixture](../tests/fixtures/m5p-toronto-live.json), with the
original `REJECTED` status retained. Present malformed fields, invalid prices,
missing quantities, sequence gaps, stale clocks and genuine empty depth still
fail closed. No historical observation is retroactively upgraded.
