from decimal import Decimal


def compute_capital_pnl(entry_price: Decimal, exit_price: Decimal, shares: Decimal) -> Decimal:
    return (exit_price - entry_price) * shares


def compute_covered_call_return_pct(premium_total: Decimal, cost_basis: Decimal) -> Decimal:
    """Return premium_total / cost_basis. cost_basis = avg_entry_price * shares of underlying."""
    if cost_basis <= 0:
        return Decimal("0")
    return premium_total / cost_basis


def compute_total_return_pct(
    capital_pnl: Decimal, dividends: Decimal, premiums: Decimal, cost_basis: Decimal
) -> Decimal:
    if cost_basis <= 0:
        return Decimal("0")
    return (capital_pnl + dividends + premiums) / cost_basis


def classify_outcome(total_return_pct: Decimal) -> str:
    if total_return_pct > 0:
        return "win"
    if total_return_pct < 0:
        return "loss"
    return "breakeven"


def is_call_itm(strike: Decimal, close_price: Decimal) -> bool:
    """Return True if the call would be assigned: close_price >= strike (ATM counts)."""
    return close_price >= strike


def compute_assignment_gain(
    strike: Decimal, avg_entry_price: Decimal, shares: Decimal
) -> Decimal:
    gain = (strike - avg_entry_price) * shares
    return gain if gain > 0 else Decimal("0")


def compute_adjusted_return_pct(start_adj_close: Decimal, end_adj_close: Decimal) -> Decimal:
    """Total return implied by adjusted closes (dividends are baked into adj_close)."""
    if start_adj_close <= 0:
        return Decimal("0")
    return (end_adj_close - start_adj_close) / start_adj_close
