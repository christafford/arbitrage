# Prompts for Codex

## First session (paste into Codex)

> Read AGENTS.md and all docs/ markdown in full. Inspect the repository and run the offline test suite plus `predarb demo` and `predarb report`. Do not mark tests passed unless you execute them. Then implement **only M1** from docs/ROADMAP.md: verify current official Kalshi and Polymarket US (NOT international) public market data APIs; implement robust paginated metadata and selected book capture, archive raw samples, add strict validation and tests with sanitized fixtures. No trading code, keys, fuzzy live matching, or fake confidence. Where actual connectivity is unavailable, document the blocker and use explicitly labeled fixtures. Update roadmap with precise evidence and remaining gaps. Keep changes small and readable.

## Second session (after M1 passes)

> Implement only M2 from ROADMAP. Build an audited human-reviewed pair registry with exact resolution text and version hashes. Test rejection of seemingly identical but semantically different questions. Never authorize a pairing by title similarity or LLM output alone. Run tests and demonstrate review/revoke CLI actions.

## Routine follow-up

> Read AGENTS.md and the current roadmap. Show incomplete acceptance criteria for the earliest unfinished milestone; implement them and their tests, run evidence-producing commands, document actual results, and stop before the next milestone. Never introduce order placement or live-trade credentials.
