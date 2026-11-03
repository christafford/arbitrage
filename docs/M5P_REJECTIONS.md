# M5P per-pair rejection breakdown

All counts come from the immutable M5O observations. Primary attribution uses a fixed reporting hierarchy (processing, integrity/continuity, structure/metadata, age, skew; lexical within groups). It is not a causal-independence estimate. Simultaneous failure counts overlap. For 1,355 processing-error samples, further unassessed venue failures remain UNKNOWN.

| Pair | Samples | Passes | Any Kalshi failure | Any US failure | Cross-venue failure | Processing error |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| cpi | 17224 | 23 | 15767 | 17068 | 17152 | 41 |
| fed-hold | 17218 | 6 | 16038 | 17090 | 17161 | 46 |
| gas-high | 17219 | 21 | 15800 | 17102 | 17138 | 50 |
| nba-boston | 2092 | 33 | 553 | 1795 | 1745 | 254 |
| nba-brooklyn | 3326 | 44 | 1018 | 2987 | 2962 | 275 |
| nba-toronto | 5952 | 51 | 3684 | 5657 | 5647 | 212 |
| nfl-arizona | 1217 | 49 | 257 | 911 | 896 | 240 |
| nfl-baltimore | 750 | 5 | 69 | 673 | 657 | 72 |
| nfl-chicago | 17132 | 137 | 9529 | 16797 | 16808 | 83 |
| payrolls | 17231 | 7 | 16071 | 17098 | 17180 | 42 |
| unemployment | 17232 | 9 | 16054 | 17130 | 17179 | 40 |

[Exact per-reason CSV](evidence/M5P_REJECTIONS.csv) separates primary, additional and all occurrences. [Full JSON](evidence/M5P_HISTORY.json) also records each simultaneous-reason combination, enabling alternative explicit attribution without changing historical judgments.

Total: 116,593 observed samples, 385 passes, 116,208 rejects. The 190,080 planned five-second pair-samples remain a separate full-window denominator. Missing samples are not silently assigned a venue error.
