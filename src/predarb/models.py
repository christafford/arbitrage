from dataclasses import dataclass
from decimal import Decimal

@dataclass(frozen=True)
class AskLevel:
    price: Decimal       # dollars per $1 payout
    quantity: Decimal    # contracts

    def __post_init__(self):
        if not self.price.is_finite() or not (Decimal("0") < self.price < Decimal("1")):
            raise ValueError("price must be finite and strictly between 0 and 1")
        if not self.quantity.is_finite() or self.quantity <= 0:
            raise ValueError("quantity must be finite and positive")

@dataclass(frozen=True)
class Evaluation:
    contracts: Decimal
    yes_cost: Decimal
    no_cost: Decimal
    fees: Decimal
    reserve: Decimal
    net_profit: Decimal
    capital: Decimal

    @property
    def roi(self):
        return self.net_profit / self.capital if self.capital else Decimal("0")
