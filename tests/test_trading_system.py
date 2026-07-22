"""
Unit tests for PortfolioGuard Quantitative Trading System.
Run with: pytest tests/ -v
"""

import numpy as np
import pandas as pd
import pytest
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from main import (
    TA,
    SignalEngine,
    SignalType,
    StrategyName,
    PaperPortfolio,
    RiskManager,
    RiskLimits,
    OrderRequest,
    OrderSide,
    OrderStatus,
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Fixtures
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@pytest.fixture
def trending_up():
    """Generate a clear uptrend price series."""
    np.random.seed(42)
    n = 120
    trend = np.linspace(100, 130, n)
    noise = np.random.normal(0, 0.5, n)
    return pd.Series(trend + noise, name="close")


@pytest.fixture
def trending_down():
    """Generate a clear downtrend price series."""
    np.random.seed(42)
    n = 120
    trend = np.linspace(130, 95, n)
    noise = np.random.normal(0, 0.5, n)
    return pd.Series(trend + noise, name="close")


@pytest.fixture
def sideways():
    """Generate sideways / range-bound prices."""
    np.random.seed(42)
    n = 120
    return pd.Series(100 + np.random.normal(0, 2, n), name="close")


@pytest.fixture
def oversold_series():
    """Generate a series that ends deeply oversold (RSI < 30)."""
    np.random.seed(10)
    n = 120
    prices = [100.0]
    for i in range(1, n):
        # Mostly down moves at the end
        if i > 100:
            prices.append(prices[-1] * (1 - abs(np.random.normal(0.003, 0.002))))
        else:
            prices.append(prices[-1] * (1 + np.random.normal(0.0002, 0.01)))
    return pd.Series(prices, name="close")


@pytest.fixture
def paper_portfolio():
    """Fresh paper trading portfolio."""
    return PaperPortfolio(initial_cash=100_000)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Technical Analysis Tests
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestTA:
    def test_sma_length(self, trending_up):
        sma = TA.sma(trending_up, 20)
        assert len(sma) == len(trending_up)
        assert sma.iloc[:19].isna().all()
        assert not sma.iloc[19:].isna().any()

    def test_sma_values(self):
        series = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], dtype=float)
        sma = TA.sma(series, 3)
        assert abs(sma.iloc[2] - 2.0) < 1e-10
        assert abs(sma.iloc[9] - 9.0) < 1e-10

    def test_ema_responds_faster_than_sma(self, trending_up):
        sma = TA.sma(trending_up, 20)
        ema = TA.ema(trending_up, 20)
        # In an uptrend, EMA should be above SMA (reacts faster)
        assert ema.iloc[-1] > sma.iloc[-1]

    def test_rsi_bounded(self, trending_up):
        rsi = TA.rsi(trending_up, 14)
        valid = rsi.dropna()
        assert (valid >= 0).all()
        assert (valid <= 100).all()

    def test_rsi_uptrend_high(self, trending_up):
        rsi = TA.rsi(trending_up, 14)
        assert rsi.iloc[-1] > 50  # Should be elevated in uptrend

    def test_rsi_downtrend_low(self, trending_down):
        rsi = TA.rsi(trending_down, 14)
        assert rsi.iloc[-1] < 50

    def test_macd_structure(self, trending_up):
        macd_line, signal_line, histogram = TA.macd(trending_up)
        assert len(macd_line) == len(trending_up)
        assert len(signal_line) == len(trending_up)
        assert len(histogram) == len(trending_up)
        # Histogram = MACD - Signal
        valid_idx = histogram.dropna().index
        np.testing.assert_allclose(
            histogram.loc[valid_idx],
            (macd_line - signal_line).loc[valid_idx],
            atol=1e-10,
        )

    def test_bollinger_bands_order(self, trending_up):
        upper, mid, lower, pct_b = TA.bollinger_bands(trending_up, 20)
        valid = upper.dropna().index
        assert (upper.loc[valid] >= mid.loc[valid]).all()
        assert (mid.loc[valid] >= lower.loc[valid]).all()

    def test_bollinger_pct_b(self, trending_up):
        upper, mid, lower, pct_b = TA.bollinger_bands(trending_up, 20)
        valid = pct_b.dropna()
        # In uptrend, %B should generally be > 0.5
        assert valid.iloc[-1] > 0.3


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Signal Engine Tests
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestSignalEngine:
    def test_ma_crossover_uptrend(self, trending_up):
        signal, strength, reason, indicators = SignalEngine.ma_crossover(trending_up)
        assert signal == SignalType.BUY
        assert strength > 0
        assert "SMA20" in reason or "sma_20" in str(indicators)

    def test_ma_crossover_downtrend(self, trending_down):
        signal, strength, reason, indicators = SignalEngine.ma_crossover(trending_down)
        assert signal == SignalType.SELL
        assert strength < 0

    def test_rsi_reversion_oversold(self, oversold_series):
        signal, strength, reason, indicators = SignalEngine.rsi_reversion(
            oversold_series
        )
        # Should detect oversold condition
        assert "rsi" in indicators
        rsi_val = indicators["rsi"]
        if rsi_val < 30:
            assert signal == SignalType.BUY
            assert strength > 0

    def test_bollinger_breakout(self, trending_up):
        signal, strength, reason, indicators = SignalEngine.bollinger_breakout(
            trending_up
        )
        assert "bb_position" in indicators
        assert "bb_upper" in indicators
        assert "bb_lower" in indicators

    def test_macd_momentum(self, trending_up):
        signal, strength, reason, indicators = SignalEngine.macd_momentum(trending_up)
        assert "macd" in indicators
        assert "macd_signal" in indicators
        assert "macd_histogram" in indicators

    def test_combined_signal(self, trending_up):
        signal, strength, reason, indicators = SignalEngine.combined_signal(trending_up)
        assert "buy_signals" in indicators
        assert "sell_signals" in indicators
        assert "consensus_strength" in indicators

    def test_generate_returns_signal_model(self, trending_up):
        sig = SignalEngine.generate("AAPL", trending_up, StrategyName.COMBINED)
        assert sig.ticker == "AAPL"
        assert sig.strategy == "combined"
        assert sig.signal in [SignalType.BUY, SignalType.SELL, SignalType.HOLD]
        assert -1 <= sig.strength <= 1
        assert sig.price > 0

    def test_all_strategies_produce_valid_output(self, trending_up):
        for strat in StrategyName:
            sig = SignalEngine.generate("TEST", trending_up, strat)
            assert sig.signal in [SignalType.BUY, SignalType.SELL, SignalType.HOLD]
            assert -1 <= sig.strength <= 1


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Paper Trading Tests
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestPaperPortfolio:
    def test_initial_state(self, paper_portfolio):
        state = paper_portfolio.get_state()
        assert state.cash == 100_000
        assert state.total_equity == 100_000
        assert state.num_positions == 0
        assert state.total_pnl == 0

    def test_buy_order(self, paper_portfolio):
        order = OrderRequest(
            ticker="AAPL", side=OrderSide.BUY, quantity=10, reason="test"
        )
        result = paper_portfolio.execute_order(order, 150.0, "Technology")

        assert result.status == OrderStatus.FILLED
        assert result.price == 150.0
        assert result.quantity == 10
        assert "AAPL" in paper_portfolio.positions
        assert paper_portfolio.positions["AAPL"]["quantity"] == 10
        assert paper_portfolio.cash < 100_000  # Spent money

    def test_sell_order(self, paper_portfolio):
        # First buy
        buy = OrderRequest(
            ticker="AAPL", side=OrderSide.BUY, quantity=10, reason="test"
        )
        paper_portfolio.execute_order(buy, 150.0, "Technology")

        # Then sell
        sell = OrderRequest(
            ticker="AAPL", side=OrderSide.SELL, quantity=10, reason="test"
        )
        result = paper_portfolio.execute_order(sell, 160.0, "Technology")

        assert result.status == OrderStatus.FILLED
        assert "AAPL" not in paper_portfolio.positions
        assert paper_portfolio.cash > 100_000 - 10  # Made profit minus commissions

    def test_sell_more_than_owned_rejected(self, paper_portfolio):
        buy = OrderRequest(ticker="AAPL", side=OrderSide.BUY, quantity=5, reason="test")
        paper_portfolio.execute_order(buy, 150.0, "Technology")

        sell = OrderRequest(
            ticker="AAPL", side=OrderSide.SELL, quantity=10, reason="test"
        )
        result = paper_portfolio.execute_order(sell, 150.0, "Technology")

        assert result.status == OrderStatus.REJECTED

    def test_insufficient_cash_rejected(self, paper_portfolio):
        # Try to buy more than we can afford
        order = OrderRequest(
            ticker="BRK.A", side=OrderSide.BUY, quantity=1000, reason="test"
        )
        result = paper_portfolio.execute_order(order, 500_000.0)

        assert result.status == OrderStatus.REJECTED

    def test_position_averaging(self, paper_portfolio):
        buy1 = OrderRequest(
            ticker="AAPL", side=OrderSide.BUY, quantity=10, reason="test"
        )
        paper_portfolio.execute_order(buy1, 100.0, "Technology")

        buy2 = OrderRequest(
            ticker="AAPL", side=OrderSide.BUY, quantity=10, reason="test"
        )
        paper_portfolio.execute_order(buy2, 200.0, "Technology")

        pos = paper_portfolio.positions["AAPL"]
        assert pos["quantity"] == 20
        assert abs(pos["avg_cost"] - 150.0) < 0.01

    def test_commission_applied(self, paper_portfolio):
        order = OrderRequest(
            ticker="AAPL", side=OrderSide.BUY, quantity=100, reason="test"
        )
        result = paper_portfolio.execute_order(order, 100.0)

        assert result.commission >= 1.0
        expected_cash = 100_000 - (100 * 100.0) - result.commission
        assert abs(paper_portfolio.cash - expected_cash) < 0.01

    def test_portfolio_equity_updates(self, paper_portfolio):
        order = OrderRequest(
            ticker="AAPL", side=OrderSide.BUY, quantity=10, reason="test"
        )
        paper_portfolio.execute_order(order, 100.0, "Technology")

        paper_portfolio.positions["AAPL"]["current_price"] = 120.0
        state = paper_portfolio.get_state()

        assert state.total_equity > 100_000  # Price went up
        assert state.positions[0].unrealized_pnl > 0

    def test_order_history(self, paper_portfolio):
        order = OrderRequest(
            ticker="AAPL", side=OrderSide.BUY, quantity=10, reason="test"
        )
        paper_portfolio.execute_order(order, 100.0)

        assert len(paper_portfolio.orders) == 1
        assert paper_portfolio.orders[0]["ticker"] == "AAPL"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Risk Manager Tests
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestRiskManager:
    def test_position_size_limit(self, paper_portfolio):
        rm = RiskManager(RiskLimits(max_position_pct=0.10))
        order = OrderRequest(
            ticker="AAPL", side=OrderSide.BUY, quantity=100, reason="test"
        )
        # 100 shares at $150 = $15,000 = 15% > 10% limit
        check = rm.check_order(order, 150.0, paper_portfolio)
        assert not check.passed
        assert not check.checks["position_size"]

    def test_position_within_limit(self, paper_portfolio):
        rm = RiskManager(RiskLimits(max_position_pct=0.20))
        order = OrderRequest(
            ticker="AAPL", side=OrderSide.BUY, quantity=10, reason="test"
        )
        # 10 shares at $150 = $1,500 = 1.5% < 20% limit
        check = rm.check_order(order, 150.0, paper_portfolio)
        assert check.passed

    def test_max_positions_limit(self, paper_portfolio):
        rm = RiskManager(RiskLimits(max_positions=2))
        # Add 2 positions
        paper_portfolio.positions["AAPL"] = {
            "quantity": 10,
            "avg_cost": 100,
            "current_price": 100,
        }
        paper_portfolio.positions["MSFT"] = {
            "quantity": 10,
            "avg_cost": 100,
            "current_price": 100,
        }

        order = OrderRequest(
            ticker="GOOGL", side=OrderSide.BUY, quantity=5, reason="test"
        )
        check = rm.check_order(order, 100.0, paper_portfolio)
        assert not check.passed
        assert not check.checks["max_positions"]

    def test_daily_loss_circuit_breaker(self, paper_portfolio):
        rm = RiskManager(RiskLimits(max_daily_loss=1000))
        paper_portfolio.day_pnl = -1500  # Already lost $1500

        order = OrderRequest(
            ticker="AAPL", side=OrderSide.BUY, quantity=1, reason="test"
        )
        check = rm.check_order(order, 100.0, paper_portfolio)
        assert not check.passed
        assert not check.checks["daily_loss_limit"]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Integration Tests
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestIntegration:
    def test_signal_to_trade_flow(self, trending_up, paper_portfolio):
        """Test the full signal → order → execution flow."""
        sig = SignalEngine.generate("AAPL", trending_up, StrategyName.COMBINED)

        if sig.signal == SignalType.BUY:
            shares = max(1, int(paper_portfolio.total_equity * 0.10 / sig.price))
            order = OrderRequest(
                ticker="AAPL",
                side=OrderSide.BUY,
                quantity=shares,
                reason=sig.reason,
            )
            result = paper_portfolio.execute_order(order, sig.price, "Technology")
            assert result.status == OrderStatus.FILLED
            assert "AAPL" in paper_portfolio.positions

    def test_round_trip_trade(self, paper_portfolio):
        """Buy then sell, verify P&L accounting."""
        buy = OrderRequest(
            ticker="AAPL", side=OrderSide.BUY, quantity=10, reason="test"
        )
        paper_portfolio.execute_order(buy, 100.0, "Technology")

        sell = OrderRequest(
            ticker="AAPL", side=OrderSide.SELL, quantity=10, reason="test"
        )
        paper_portfolio.execute_order(sell, 110.0, "Technology")

        state = paper_portfolio.get_state()
        # Should have profit minus commissions
        assert state.total_pnl > 0 or state.total_pnl > -10  # Small commission impact

    def test_multiple_positions(self, paper_portfolio):
        """Manage multiple positions simultaneously."""
        tickers = [("AAPL", 150.0), ("MSFT", 300.0), ("GOOGL", 140.0)]

        for ticker, price in tickers:
            order = OrderRequest(
                ticker=ticker, side=OrderSide.BUY, quantity=5, reason="test"
            )
            result = paper_portfolio.execute_order(order, price, "Technology")
            assert result.status == OrderStatus.FILLED

        state = paper_portfolio.get_state()
        assert state.num_positions == 3
        assert state.cash < 100_000

        # Verify weights sum to ~1 (with cash)
        total_weight = sum(p.weight for p in state.positions)
        cash_weight = state.cash / state.total_equity
        assert abs(total_weight + cash_weight - 1.0) < 0.01
