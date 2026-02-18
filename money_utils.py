"""Money rounding and formatting helpers.

Rounding policy is intentionally biased to benefit the house.
"""

from decimal import Decimal, ROUND_DOWN, ROUND_UP, ROUND_HALF_UP

CENT = Decimal("0.01")


def _to_decimal(value):
    return Decimal(str(value))


def house_round_credit(value):
    # Player credit: round down to reduce payout.
    return float(_to_decimal(value).quantize(CENT, rounding=ROUND_DOWN))


def house_round_charge(value):
    # Player charge magnitude: round up to increase charge.
    return float(_to_decimal(value).quantize(CENT, rounding=ROUND_UP))


def house_round_delta(delta):
    # Signed account change where positive credits and negative debits the player.
    decimal_delta = _to_decimal(delta)
    if decimal_delta >= 0:
        rounded = decimal_delta.quantize(CENT, rounding=ROUND_DOWN)
    else:
        rounded = -(abs(decimal_delta).quantize(CENT, rounding=ROUND_UP))
    return float(rounded)


def house_round_balance(balance):
    # Normalize balances to cents in the same house-favor direction by sign.
    decimal_balance = _to_decimal(balance)
    if decimal_balance >= 0:
        rounded = decimal_balance.quantize(CENT, rounding=ROUND_DOWN)
    else:
        rounded = decimal_balance.quantize(CENT, rounding=ROUND_UP)
    return float(rounded)


def format_money(value):
    # Stable display format for currency.
    rounded = _to_decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)
    return f"{rounded:.2f}"
