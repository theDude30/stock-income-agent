from app.sources.base import FundamentalsSnapshot
from app.sources.fakes import InMemoryFundamentalsSource


def test_fake_fundamentals_returns_snapshots():
    snap = FundamentalsSnapshot(
        fiscal_period="2026Q1", revenue=100.0, eps=2.0, fcf=30.0,
        net_income=20.0, total_debt=50.0, total_equity=80.0, dividends_paid=10.0,
    )
    src = InMemoryFundamentalsSource({"KO": [snap]})
    assert list(src.fetch("KO")) == [snap]
    assert list(src.fetch("MISSING")) == []
