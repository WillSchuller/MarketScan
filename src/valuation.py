"""Estimate buy-and-hold returns after entry fees and rank positive net ROI."""

from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING


@dataclass(frozen=True)
class FeePolicy:
    contracts: int = 1
    taker_multiplier: Decimal = Decimal(1)
    balance_precision: Decimal = Decimal('0.0001')

    def __post_init__(self) -> None:
        if type(self.contracts) is not int or self.contracts <= 0:
            raise ValueError('EV_CONTRACTS must be a positive integer.')
        if not self.taker_multiplier.is_finite() or self.taker_multiplier < 0:
            raise ValueError('KALSHI_TAKER_FEE_MULTIPLIER must be finite and nonnegative.')
        if self.balance_precision not in (Decimal('0.0001'), Decimal('0.01')):
            raise ValueError('KALSHI_BALANCE_PRECISION must be 0.0001 or 0.01.')
        # Decimal.quantize uses the exponent, so .010 must become .01.
        object.__setattr__(self, 'balance_precision', self.balance_precision.normalize())


@dataclass(frozen=True)
class NetValue:
    fair_probability: Decimal
    price: Decimal
    contracts: int
    entry_cost: Decimal
    entry_fee: Decimal
    total_cost: Decimal
    expected_profit: Decimal
    gross_ev: Decimal
    net_ev: Decimal


@dataclass(frozen=True)
class Opportunity:
    description: str
    ticker: str
    side: str
    value: NetValue


def calculate_net_value(
    fair_probability: Decimal | None,
    price: Decimal | None,
    policy: FeePolicy = FeePolicy(),
) -> NetValue | None:
    """Estimate one equivalent taker buy fill, held to standard binary settlement.

    July 2026 fee schedule: model fee = .07 * M * C * P * (1-P).
    Trade fees round upward to $0.000001; round cost + fee upward to the
    account's balance precision. Fees are charged on entry, regardless of win.
    See https://docs.kalshi.com/getting_started/fee_rounding .
    """
    if fair_probability is None or price is None:
        return None
    if not fair_probability.is_finite() or not price.is_finite():
        return None
    if not (0 < fair_probability < 1 and 0 < price < 1):
        return None

    entry_cost = policy.contracts * price
    model_fee = Decimal('0.07') * policy.taker_multiplier * entry_cost * (1-price)
    trade_fee = model_fee.quantize(Decimal('0.000001'), rounding=ROUND_CEILING)
    total_cost = (entry_cost + trade_fee).quantize(
        policy.balance_precision, rounding=ROUND_CEILING
    )
    entry_fee = total_cost - entry_cost
    expected_profit = policy.contracts * fair_probability - total_cost
    return NetValue(
        fair_probability=fair_probability,
        price=price,
        contracts=policy.contracts,
        entry_cost=entry_cost,
        entry_fee=entry_fee,
        total_cost=total_cost,
        expected_profit=expected_profit,
        gross_ev=(fair_probability-price)/price,
        net_ev=expected_profit/total_cost,
    )


def rank_opportunities(opportunities: list[Opportunity]) -> list[Opportunity]:
    """Rank unrounded net ROI, then expected profit, with deterministic ties."""
    return sorted(
        (item for item in opportunities if item.value.net_ev > 0),
        key=lambda item: (
            -item.value.net_ev,
            -item.value.expected_profit,
            item.ticker,
            item.side,
        ),
    )
