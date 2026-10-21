"""Hypothetical, exact Decimal evaluation for manually verified complementary contracts."""
from decimal import Decimal
from .models import AskLevel, Evaluation


def evaluate(yes_asks: list[AskLevel], no_asks: list[AskLevel], *,
             max_pairs: Decimal, fee_per_pair: Decimal, reserve_per_pair: Decimal = Decimal("0")) -> Evaluation:
    """Take adjacent cheapest price levels on each side and stop before negative marginal net edge.

    Does NOT prove rule equivalence, simultaneous fills, or actual fee schedules.
    All input fee/reserve values are explicit DOLLARS per matched pair.
    """
    if not max_pairs.is_finite() or max_pairs <= 0:
        raise ValueError("max_pairs must be positive and finite")
    if any(not x.is_finite() or x < 0 for x in (fee_per_pair, reserve_per_pair)):
        raise ValueError("fees/reserve must be nonnegative finite")
    for book in (yes_asks, no_asks):
        if any(book[i].price > book[i+1].price for i in range(len(book)-1)):
            raise ValueError("asks must be sorted cheapest first")
    i = j = 0
    ry = rn = Decimal("0")
    q = yc = nc = Decimal("0")
    while i < len(yes_asks) and j < len(no_asks) and q < max_pairs:
        y, n = yes_asks[i], no_asks[j]
        if ry == 0: ry = y.quantity
        if rn == 0: rn = n.quantity
        marginal = Decimal("1") - y.price - n.price - fee_per_pair - reserve_per_pair
        if marginal <= 0:
            break
        take = min(ry, rn, max_pairs - q)
        q += take
        yc += take * y.price
        nc += take * n.price
        ry -= take
        rn -= take
        if ry == 0: i += 1
        if rn == 0: j += 1
    fees = q * fee_per_pair
    reserve = q * reserve_per_pair
    capital = yc + nc + fees + reserve
    profit = q - capital
    return Evaluation(q, yc, nc, fees, reserve, profit, capital)
