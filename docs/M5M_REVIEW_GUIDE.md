# M5M human review guide

Start with the [CPI above 0.2% packet](m5m/cpi-two.md). The exceptional rules are
more important than the ordinary threshold. The assistant found revision/fallback
conflicts and recommends exclusion from strict arbitrage; your decision is pending.

The five prepared packets are:

| Packet | Primary question |
| --- | --- |
| [CPI above 0.0%](m5m/cpi-zero.md) | Initial release versus expiration value; incompatible missing-data fallbacks |
| [CPI above 0.2%](m5m/cpi-two.md) | Same exception family at a different threshold |
| [CPI above 0.5%](m5m/cpi-five.md) | Same exception family at a different threshold |
| [Gas below $3.20](m5m/gas-low.md) | March issuance versus September 9 observation start |
| [Gas above $4.60](m5m/gas-high.md) | Issuance boundary versus September 9; source/revision exceptions |

These are five market pairs across two economic event families, not five distinct
independent research discoveries. All ten markets were open at their recorded
November 1 UTC retrievals. Availability and fees can change.

## What to check

1. Open both official definition links and product PDFs in a packet. Compare them
   with the captured copies; note changes rather than silently replacing evidence.
2. Check the statistic, geography, observation interval, threshold and equality
   case. Then walk the packet's revision, missing-publication, cancellation,
   suspension and source-substitution cases.
3. For each case, establish the selected-leg payout on both venues. The supported
   route is Kalshi long NO plus US long YES. If the sum can be below $1 or cannot
   be established, record the difference. Do not assume independent fair prices
   are equal or automatically use $0.50.
4. Review the fee packets, collateral/account scope and cash timing separately.
   Public parameters do not confirm your account's precision, extras or funding.
5. Record **REJECTED**, **UNRESOLVED**, or a complete source-backed review. A
   settlement-compatible decision requires all existing registry, mechanics and
   fee checks; reading this packet or writing “looks good” is not approval.

A useful review note is:

```text
Packet:
Reviewer and UTC date:
Decision: REJECTED / UNRESOLVED
Official source and clause/page:
Scenario where payouts differ or remain unknown:
Question requiring venue clarification:
Fee/account review: pending / findings
```

The linked `*-human-review.json` files are blank existing-registry forms. Do not
fill `equivalent: true` for an unresolved comparison. A rejection can be recorded
with the existing `pairs reject` command after you explicitly make that decision;
the assistant has not issued that command on your behalf. Proposed IDs 1–5 belong
only to `data/m5m/non-sports/research.sqlite3`, not the production database.

Approvals expire and bind exact source versions. No expired approval is renewed.
The full [pair workflow](PAIR_REVIEW.md), [fee review](FEE_REVIEW.md), and
[mechanics guide](SETTLEMENT_MECHANICS.md) remain authoritative. The current packets
contain substantial conflicts, so live economic calculations remain blocked.
Human review never authorizes real-money trading.
