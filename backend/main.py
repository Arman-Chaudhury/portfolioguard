"""
PortfolioGuard — Quantitative Trading System
Backend API: FastAPI + Yahoo Finance

Modules:
  - MarketDataService:   price feeds, ticker metadata, caching
  - TechnicalAnalysis:   RSI, MACD, Bollinger Bands, moving averages, ATR
  - SignalEngine:        strategy-driven BUY / SELL / HOLD signal generation
  - Backtester:          historical strategy replay with transaction costs
  - PaperTradingEngine:  simulated execution, position & P&L tracking
  - RiskManager:         pre-trade checks, drawdown breakers, exposure limits
"""

import numpy as np
import pandas as pd
import yfinance as yf
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timedelta, timezone
from enum import Enum
import logging
import time
import uuid

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  App Configuration
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("portfolioguard")

app = FastAPI(
    title="PortfolioGuard Trading API",
    description="Quantitative trading system with signals, backtesting, paper trading, and risk management",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Enums & Pydantic Models
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class SignalType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, Enum):
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    PENDING = "PENDING"


class StrategyName(str, Enum):
    MA_CROSSOVER = "ma_crossover"
    RSI_REVERSION = "rsi_reversion"
    BOLLINGER_BREAKOUT = "bollinger_breakout"
    MACD_MOMENTUM = "macd_momentum"
    COMBINED = "combined"


class Signal(BaseModel):
    ticker: str
    strategy: str
    signal: SignalType
    strength: float = Field(ge=-1, le=1)
    price: float
    reason: str
    timestamp: str
    indicators: dict = {}


class ScanRequest(BaseModel):
    tickers: list[str]
    strategy: StrategyName = StrategyName.COMBINED


class OrderRequest(BaseModel):
    ticker: str
    side: OrderSide
    quantity: int = Field(gt=0, le=10000)
    reason: str = ""


class Order(BaseModel):
    order_id: str
    ticker: str
    side: OrderSide
    quantity: int
    price: float
    total: float
    commission: float
    status: OrderStatus
    reason: str
    timestamp: str
    rejection_reason: str = ""


class Position(BaseModel):
    ticker: str
    quantity: int
    avg_cost: float
    current_price: float
    market_value: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    weight: float
    day_change_pct: float


class PortfolioState(BaseModel):
    cash: float
    total_equity: float
    positions_value: float
    total_pnl: float
    total_pnl_pct: float
    day_pnl: float
    positions: list[Position]
    buying_power: float
    num_positions: int


class RiskLimits(BaseModel):
    max_position_pct: float = 0.20
    max_daily_loss: float = 5000.0
    max_positions: int = 15
    stop_loss_pct: float = 0.08


class RiskCheck(BaseModel):
    passed: bool
    checks: dict[str, bool]
    violations: list[str]


class BacktestRequest(BaseModel):
    tickers: list[str]
    strategy: StrategyName = StrategyName.MA_CROSSOVER
    initial_capital: float = Field(default=100_000, gt=0)
    lookback_days: int = Field(default=504, ge=60, le=2520)
    commission_pct: float = Field(default=0.001, ge=0, le=0.01)
    position_size_pct: float = Field(default=0.10, gt=0, le=0.5)


class BacktestTrade(BaseModel):
    date: str
    ticker: str
    side: str
    price: float
    quantity: int
    pnl: float = 0.0


class BacktestResult(BaseModel):
    strategy: str
    total_return: float
    annualized_return: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    win_rate: float
    total_trades: int
    avg_win: float
    avg_loss: float
    profit_factor: float
    equity_curve: list[dict]
    trades: list[BacktestTrade]
    monthly_returns: list[dict]
    benchmark_return: float


class QuoteResponse(BaseModel):
    ticker: str
    name: str
    price: float
    change: float
    change_pct: float
    volume: int
    market_cap: int
    sector: str
    pe_ratio: Optional[float] = None
    dividend_yield: Optional[float] = None
    fifty_two_week_high: Optional[float] = None
    fifty_two_week_low: Optional[float] = None


class WatchlistSignal(BaseModel):
    ticker: str
    name: str
    price: float
    change_pct: float
    sector: str
    signal: SignalType
    strength: float
    strategy: str
    reason: str
    rsi: Optional[float] = None
    macd_histogram: Optional[float] = None
    bb_position: Optional[float] = None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Market Data Service
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class MarketDataService:
    CACHE_TTL = 300
    BENCHMARK = "SPY"

    def __init__(self):
        self._cache: dict[str, tuple[float, pd.DataFrame]] = {}
        self._info_cache: dict[str, tuple[float, dict]] = {}

    def fetch_prices(self, tickers: list[str], period_days: int = 252) -> pd.DataFrame:
        cache_key = f"{','.join(sorted(tickers))}_{period_days}"
        now = time.time()

        if cache_key in self._cache:
            ts, data = self._cache[cache_key]
            if now - ts < self.CACHE_TTL:
                return data

        end = datetime.now()
        start = end - timedelta(days=int(period_days * 1.5))

        try:
            data = yf.download(
                tickers,
                start=start.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d"),
                auto_adjust=True,
                progress=False,
            )
            if data.empty:
                raise ValueError("No data from Yahoo Finance")

            if len(tickers) == 1:
                prices = data[["Close"]].copy()
                prices.columns = tickers
            else:
                prices = data["Close"].copy()

            prices = prices.ffill().dropna(how="all").tail(period_days)
            self._cache[cache_key] = (now, prices)
            return prices
        except Exception as e:
            logger.error(f"Fetch failed: {e}")
            raise HTTPException(status_code=502, detail=f"Market data unavailable: {e}")

    def fetch_ohlcv(self, ticker: str, period_days: int = 252) -> pd.DataFrame:
        cache_key = f"ohlcv_{ticker}_{period_days}"
        now = time.time()

        if cache_key in self._cache:
            ts, data = self._cache[cache_key]
            if now - ts < self.CACHE_TTL:
                return data

        end = datetime.now()
        start = end - timedelta(days=int(period_days * 1.5))

        try:
            data = yf.download(
                ticker,
                start=start.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d"),
                auto_adjust=True,
                progress=False,
            )
            if data.empty:
                raise ValueError(f"No data for {ticker}")

            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.get_level_values(0)

            data = data.tail(period_days)
            self._cache[cache_key] = (now, data)
            return data
        except Exception as e:
            logger.error(f"OHLCV fetch failed for {ticker}: {e}")
            raise HTTPException(status_code=502, detail=f"Market data unavailable: {e}")

    def get_ticker_info(self, ticker: str) -> dict:
        now = time.time()
        if ticker in self._info_cache:
            ts, info = self._info_cache[ticker]
            if now - ts < 3600:
                return info

        try:
            info = yf.Ticker(ticker).info
            result = {
                "name": info.get("shortName", ticker),
                "sector": info.get("sector", "Unknown"),
                "industry": info.get("industry", "Unknown"),
                "market_cap": info.get("marketCap", 0),
                "pe_ratio": info.get("trailingPE"),
                "dividend_yield": info.get("dividendYield"),
                "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
                "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
            }
            self._info_cache[ticker] = (now, result)
            return result
        except Exception:
            return {
                "name": ticker,
                "sector": "Unknown",
                "industry": "Unknown",
                "market_cap": 0,
                "pe_ratio": None,
                "dividend_yield": None,
                "fifty_two_week_high": None,
                "fifty_two_week_low": None,
            }


mkt = MarketDataService()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Technical Analysis Library
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TA:
    """Stateless technical indicator computations."""

    @staticmethod
    def sma(series: pd.Series, period: int) -> pd.Series:
        return series.rolling(window=period).mean()

    @staticmethod
    def ema(series: pd.Series, period: int) -> pd.Series:
        return series.ewm(span=period, adjust=False).mean()

    @staticmethod
    def rsi(series: pd.Series, period: int = 14) -> pd.Series:
        delta = series.diff()
        gain = delta.where(delta > 0, 0.0).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(window=period).mean()
        rs = gain / loss.replace(0, np.nan)
        return 100 - (100 / (1 + rs))

    @staticmethod
    def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
        ema_fast = series.ewm(span=fast, adjust=False).mean()
        ema_slow = series.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram

    @staticmethod
    def bollinger_bands(series: pd.Series, period: int = 20, std_dev: float = 2.0):
        sma = series.rolling(window=period).mean()
        std = series.rolling(window=period).std()
        upper = sma + std_dev * std
        lower = sma - std_dev * std
        pct_b = (series - lower) / (upper - lower).replace(0, np.nan)
        return upper, sma, lower, pct_b

    @staticmethod
    def atr(
        high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
    ) -> pd.Series:
        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.rolling(window=period).mean()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Signal Engine — Strategy Implementations
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class SignalEngine:
    """Generates trading signals from technical indicators."""

    @staticmethod
    def ma_crossover(
        close: pd.Series, fast: int = 20, slow: int = 50
    ) -> tuple[SignalType, float, str, dict]:
        sma_fast = TA.sma(close, fast)
        sma_slow = TA.sma(close, slow)

        if sma_fast.iloc[-1] is np.nan or sma_slow.iloc[-1] is np.nan:
            return SignalType.HOLD, 0.0, "Insufficient data", {}

        fast_val = float(sma_fast.iloc[-1])
        slow_val = float(sma_slow.iloc[-1])
        prev_fast = float(sma_fast.iloc[-2]) if len(sma_fast) > 1 else fast_val
        prev_slow = float(sma_slow.iloc[-2]) if len(sma_slow) > 1 else slow_val
        spread_pct = (fast_val - slow_val) / slow_val if slow_val != 0 else 0

        indicators = {
            f"sma_{fast}": round(fast_val, 2),
            f"sma_{slow}": round(slow_val, 2),
            "spread_pct": round(spread_pct * 100, 3),
        }

        if prev_fast <= prev_slow and fast_val > slow_val:
            return (
                SignalType.BUY,
                min(0.9, abs(spread_pct) * 20),
                f"SMA{fast} crossed above SMA{slow} — bullish crossover",
                indicators,
            )
        if prev_fast >= prev_slow and fast_val < slow_val:
            return (
                SignalType.SELL,
                min(0.9, abs(spread_pct) * 20) * -1,
                f"SMA{fast} crossed below SMA{slow} — bearish crossover",
                indicators,
            )

        if fast_val > slow_val:
            return (
                SignalType.BUY,
                min(0.6, spread_pct * 10),
                f"SMA{fast} above SMA{slow} — uptrend",
                indicators,
            )
        elif fast_val < slow_val:
            return (
                SignalType.SELL,
                max(-0.6, spread_pct * 10),
                f"SMA{fast} below SMA{slow} — downtrend",
                indicators,
            )

        return SignalType.HOLD, 0.0, "Moving averages converging", indicators

    @staticmethod
    def rsi_reversion(
        close: pd.Series, period: int = 14, oversold: float = 30, overbought: float = 70
    ) -> tuple[SignalType, float, str, dict]:
        rsi = TA.rsi(close, period)

        if rsi.iloc[-1] is np.nan:
            return SignalType.HOLD, 0.0, "Insufficient data", {}

        rsi_val = float(rsi.iloc[-1])
        prev_rsi = float(rsi.iloc[-2]) if len(rsi) > 1 else rsi_val
        indicators = {
            "rsi": round(rsi_val, 2),
            "oversold": oversold,
            "overbought": overbought,
        }

        if rsi_val < oversold:
            strength = min(1.0, (oversold - rsi_val) / oversold)
            if prev_rsi >= oversold:
                return (
                    SignalType.BUY,
                    strength,
                    f"RSI({rsi_val:.1f}) entered oversold — reversal opportunity",
                    indicators,
                )
            return (
                SignalType.BUY,
                strength * 0.7,
                f"RSI({rsi_val:.1f}) oversold — mean reversion expected",
                indicators,
            )

        if rsi_val > overbought:
            strength = min(1.0, (rsi_val - overbought) / (100 - overbought))
            if prev_rsi <= overbought:
                return (
                    SignalType.SELL,
                    -strength,
                    f"RSI({rsi_val:.1f}) entered overbought — pullback likely",
                    indicators,
                )
            return (
                SignalType.SELL,
                -strength * 0.7,
                f"RSI({rsi_val:.1f}) overbought — reversion expected",
                indicators,
            )

        return SignalType.HOLD, 0.0, f"RSI({rsi_val:.1f}) neutral", indicators

    @staticmethod
    def bollinger_breakout(
        close: pd.Series, period: int = 20, std_dev: float = 2.0
    ) -> tuple[SignalType, float, str, dict]:
        upper, mid, lower, pct_b = TA.bollinger_bands(close, period, std_dev)

        if pct_b.iloc[-1] is np.nan:
            return SignalType.HOLD, 0.0, "Insufficient data", {}

        bb_pos = float(pct_b.iloc[-1])
        upper_val = float(upper.iloc[-1])
        lower_val = float(lower.iloc[-1])
        mid_val = float(mid.iloc[-1])
        band_width = (upper_val - lower_val) / mid_val if mid_val != 0 else 0

        indicators = {
            "bb_upper": round(upper_val, 2),
            "bb_mid": round(mid_val, 2),
            "bb_lower": round(lower_val, 2),
            "bb_position": round(bb_pos, 3),
            "band_width": round(band_width * 100, 2),
        }

        if bb_pos < 0:
            return (
                SignalType.BUY,
                min(1.0, abs(bb_pos)),
                "Price below lower Bollinger Band — oversold bounce expected",
                indicators,
            )
        if bb_pos > 1:
            return (
                SignalType.SELL,
                -min(1.0, bb_pos - 1),
                "Price above upper Bollinger Band — pullback expected",
                indicators,
            )
        if bb_pos < 0.2:
            return (
                SignalType.BUY,
                0.4,
                f"Price near lower band ({bb_pos:.1%}) — approaching support",
                indicators,
            )
        if bb_pos > 0.8:
            return (
                SignalType.SELL,
                -0.4,
                f"Price near upper band ({bb_pos:.1%}) — approaching resistance",
                indicators,
            )

        return SignalType.HOLD, 0.0, f"Price within bands ({bb_pos:.1%})", indicators

    @staticmethod
    def macd_momentum(close: pd.Series) -> tuple[SignalType, float, str, dict]:
        macd_line, signal_line, histogram = TA.macd(close)

        if histogram.iloc[-1] is np.nan:
            return SignalType.HOLD, 0.0, "Insufficient data", {}

        hist_val = float(histogram.iloc[-1])
        prev_hist = float(histogram.iloc[-2]) if len(histogram) > 1 else hist_val
        macd_val = float(macd_line.iloc[-1])
        signal_val = float(signal_line.iloc[-1])
        price = float(close.iloc[-1])
        norm_hist = hist_val / price if price != 0 else 0

        indicators = {
            "macd": round(macd_val, 4),
            "macd_signal": round(signal_val, 4),
            "macd_histogram": round(hist_val, 4),
        }

        if prev_hist <= 0 and hist_val > 0:
            return (
                SignalType.BUY,
                min(0.9, abs(norm_hist) * 200),
                "MACD bullish crossover — histogram turned positive",
                indicators,
            )
        if prev_hist >= 0 and hist_val < 0:
            return (
                SignalType.SELL,
                max(-0.9, -abs(norm_hist) * 200),
                "MACD bearish crossover — histogram turned negative",
                indicators,
            )

        if hist_val > 0:
            if hist_val > prev_hist:
                return (
                    SignalType.BUY,
                    min(0.6, norm_hist * 100),
                    "MACD momentum increasing — bullish",
                    indicators,
                )
            return SignalType.HOLD, 0.1, "MACD positive but momentum fading", indicators
        else:
            if hist_val < prev_hist:
                return (
                    SignalType.SELL,
                    max(-0.6, norm_hist * 100),
                    "MACD momentum decreasing — bearish",
                    indicators,
                )
            return (
                SignalType.HOLD,
                -0.1,
                "MACD negative but selling pressure fading",
                indicators,
            )

    @staticmethod
    def combined_signal(close: pd.Series) -> tuple[SignalType, float, str, dict]:
        strategies = [
            ("MA Crossover", SignalEngine.ma_crossover(close)),
            ("RSI", SignalEngine.rsi_reversion(close)),
            ("Bollinger", SignalEngine.bollinger_breakout(close)),
            ("MACD", SignalEngine.macd_momentum(close)),
        ]

        total_strength = 0.0
        reasons = []
        all_indicators = {}

        for name, (sig, strength, reason, indicators) in strategies:
            total_strength += strength
            if sig != SignalType.HOLD:
                reasons.append(f"{name}: {reason}")
            all_indicators.update(indicators)

        avg_strength = total_strength / len(strategies)
        buy_count = sum(1 for _, (s, _, _, _) in strategies if s == SignalType.BUY)
        sell_count = sum(1 for _, (s, _, _, _) in strategies if s == SignalType.SELL)
        all_indicators["consensus_strength"] = round(avg_strength, 3)
        all_indicators["buy_signals"] = buy_count
        all_indicators["sell_signals"] = sell_count

        if avg_strength > 0.15 and buy_count >= 2:
            return (
                SignalType.BUY,
                avg_strength,
                f"Consensus BUY ({buy_count}/4 agree). " + "; ".join(reasons[:2]),
                all_indicators,
            )
        if avg_strength < -0.15 and sell_count >= 2:
            return (
                SignalType.SELL,
                avg_strength,
                f"Consensus SELL ({sell_count}/4 agree). " + "; ".join(reasons[:2]),
                all_indicators,
            )

        return (
            SignalType.HOLD,
            avg_strength,
            f"Mixed signals ({buy_count} buy, {sell_count} sell) — no consensus",
            all_indicators,
        )

    @staticmethod
    def generate(ticker: str, close: pd.Series, strategy: StrategyName) -> Signal:
        dispatch = {
            StrategyName.MA_CROSSOVER: SignalEngine.ma_crossover,
            StrategyName.RSI_REVERSION: SignalEngine.rsi_reversion,
            StrategyName.BOLLINGER_BREAKOUT: SignalEngine.bollinger_breakout,
            StrategyName.MACD_MOMENTUM: SignalEngine.macd_momentum,
            StrategyName.COMBINED: SignalEngine.combined_signal,
        }
        sig, strength, reason, indicators = dispatch[strategy](close)
        return Signal(
            ticker=ticker,
            strategy=strategy.value,
            signal=sig,
            strength=round(strength, 4),
            price=round(float(close.iloc[-1]), 2),
            reason=reason,
            timestamp=datetime.now(timezone.utc).isoformat(),
            indicators=indicators,
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Risk Manager
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class RiskManager:
    def __init__(self, limits: RiskLimits = None):
        self.limits = limits or RiskLimits()

    def check_order(
        self, order: OrderRequest, price: float, portfolio: "PaperPortfolio"
    ) -> RiskCheck:
        checks = {}
        violations = []
        order_value = price * order.quantity

        # Position size limit
        if portfolio.total_equity > 0:
            pct = order_value / portfolio.total_equity
            ok = pct <= self.limits.max_position_pct
            checks["position_size"] = ok
            if not ok:
                violations.append(
                    f"Position size {pct:.1%} exceeds {self.limits.max_position_pct:.0%} limit"
                )
        else:
            checks["position_size"] = True

        # Cash check for buys
        if order.side == OrderSide.BUY:
            ok = portfolio.cash >= order_value * 1.001
            checks["buying_power"] = ok
            if not ok:
                violations.append(
                    f"Insufficient cash: need ${order_value:,.2f}, have ${portfolio.cash:,.2f}"
                )
        else:
            checks["buying_power"] = True

        # Position exists for sells
        if order.side == OrderSide.SELL:
            pos = portfolio.positions.get(order.ticker)
            ok = pos is not None and pos["quantity"] >= order.quantity
            checks["position_exists"] = ok
            if not ok:
                violations.append(
                    f"Cannot sell {order.quantity} shares of {order.ticker}"
                )
        else:
            checks["position_exists"] = True

        # Max positions
        if order.side == OrderSide.BUY and order.ticker not in portfolio.positions:
            ok = len(portfolio.positions) < self.limits.max_positions
            checks["max_positions"] = ok
            if not ok:
                violations.append(
                    f"Max positions ({self.limits.max_positions}) reached"
                )
        else:
            checks["max_positions"] = True

        # Daily loss limit
        ok = portfolio.day_pnl > -self.limits.max_daily_loss
        checks["daily_loss_limit"] = ok
        if not ok:
            violations.append(
                f"Daily loss ${abs(portfolio.day_pnl):,.2f} exceeds limit"
            )

        return RiskCheck(
            passed=all(checks.values()), checks=checks, violations=violations
        )


risk_mgr = RiskManager()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Paper Trading Portfolio
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class PaperPortfolio:
    COMMISSION_PER_SHARE = 0.005

    def __init__(self, initial_cash: float = 100_000):
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.positions: dict[str, dict] = {}
        self.orders: list[dict] = []
        self.day_pnl = 0.0
        self._last_reset_date = datetime.now(timezone.utc).date()

    def _commission(self, quantity: int) -> float:
        return max(1.0, quantity * self.COMMISSION_PER_SHARE)

    def _maybe_reset_day_pnl(self):
        today = datetime.now(timezone.utc).date()
        if today != self._last_reset_date:
            self.day_pnl = 0.0
            self._last_reset_date = today

    @property
    def total_equity(self) -> float:
        return self.cash + sum(
            p["quantity"] * p.get("current_price", p["avg_cost"])
            for p in self.positions.values()
        )

    def execute_order(
        self, order: OrderRequest, price: float, sector: str = "Unknown"
    ) -> Order:
        self._maybe_reset_day_pnl()
        commission = self._commission(order.quantity)
        total = price * order.quantity

        risk = risk_mgr.check_order(order, price, self)
        if not risk.passed:
            return Order(
                order_id=str(uuid.uuid4())[:8],
                ticker=order.ticker,
                side=order.side,
                quantity=order.quantity,
                price=price,
                total=total,
                commission=commission,
                status=OrderStatus.REJECTED,
                reason=order.reason,
                timestamp=datetime.now(timezone.utc).isoformat(),
                rejection_reason="; ".join(risk.violations),
            )

        if order.side == OrderSide.BUY:
            self.cash -= total + commission
            if order.ticker in self.positions:
                pos = self.positions[order.ticker]
                new_qty = pos["quantity"] + order.quantity
                pos["avg_cost"] = (
                    pos["avg_cost"] * pos["quantity"] + price * order.quantity
                ) / new_qty
                pos["quantity"] = new_qty
            else:
                self.positions[order.ticker] = {
                    "quantity": order.quantity,
                    "avg_cost": price,
                    "sector": sector,
                    "current_price": price,
                }
        elif order.side == OrderSide.SELL:
            self.cash += total - commission
            pos = self.positions[order.ticker]
            pnl = (price - pos["avg_cost"]) * order.quantity - commission
            self.day_pnl += pnl
            pos["quantity"] -= order.quantity
            if pos["quantity"] <= 0:
                del self.positions[order.ticker]

        result = Order(
            order_id=str(uuid.uuid4())[:8],
            ticker=order.ticker,
            side=order.side,
            quantity=order.quantity,
            price=price,
            total=total,
            commission=commission,
            status=OrderStatus.FILLED,
            reason=order.reason,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        self.orders.append(result.model_dump())
        return result

    def get_state(self) -> PortfolioState:
        self._maybe_reset_day_pnl()
        equity = self.total_equity
        positions_value = equity - self.cash

        pos_list = []
        for ticker, p in self.positions.items():
            current = p.get("current_price", p["avg_cost"])
            cost_basis = p["avg_cost"] * p["quantity"]
            mkt_val = current * p["quantity"]
            upnl = mkt_val - cost_basis

            pos_list.append(
                Position(
                    ticker=ticker,
                    quantity=p["quantity"],
                    avg_cost=round(p["avg_cost"], 2),
                    current_price=round(current, 2),
                    market_value=round(mkt_val, 2),
                    unrealized_pnl=round(upnl, 2),
                    unrealized_pnl_pct=round(upnl / cost_basis, 4)
                    if cost_basis != 0
                    else 0,
                    weight=round(mkt_val / equity, 4) if equity > 0 else 0,
                    day_change_pct=0.0,
                )
            )

        total_pnl = equity - self.initial_cash
        return PortfolioState(
            cash=round(self.cash, 2),
            total_equity=round(equity, 2),
            positions_value=round(positions_value, 2),
            total_pnl=round(total_pnl, 2),
            total_pnl_pct=round(total_pnl / self.initial_cash, 4)
            if self.initial_cash > 0
            else 0,
            day_pnl=round(self.day_pnl, 2),
            positions=sorted(pos_list, key=lambda x: x.market_value, reverse=True),
            buying_power=round(self.cash, 2),
            num_positions=len(self.positions),
        )


portfolio = PaperPortfolio(initial_cash=100_000)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Backtesting Engine
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class Backtester:
    TRADING_DAYS = 252

    @staticmethod
    def run(req: BacktestRequest) -> BacktestResult:
        all_tickers = req.tickers + [mkt.BENCHMARK]
        prices = mkt.fetch_prices(all_tickers, req.lookback_days)

        cash = req.initial_capital
        positions: dict[str, dict] = {}
        equity_curve = []
        trades = []
        daily_returns = []

        strategy_fn = {
            StrategyName.MA_CROSSOVER: SignalEngine.ma_crossover,
            StrategyName.RSI_REVERSION: SignalEngine.rsi_reversion,
            StrategyName.BOLLINGER_BREAKOUT: SignalEngine.bollinger_breakout,
            StrategyName.MACD_MOMENTUM: SignalEngine.macd_momentum,
            StrategyName.COMBINED: SignalEngine.combined_signal,
        }[req.strategy]

        warmup = 60
        if len(prices) < warmup + 10:
            raise HTTPException(
                status_code=400, detail="Insufficient data for backtesting"
            )

        prev_equity = req.initial_capital

        for i in range(warmup, len(prices)):
            date = prices.index[i]
            date_str = (
                date.strftime("%Y-%m-%d") if hasattr(date, "strftime") else str(date)
            )

            for ticker in req.tickers:
                if ticker not in prices.columns:
                    continue
                close_series = prices[ticker].iloc[: i + 1]
                if close_series.isna().iloc[-1]:
                    continue

                signal, strength, reason, _ = strategy_fn(close_series)
                price = float(close_series.iloc[-1])

                if signal == SignalType.BUY and ticker not in positions:
                    position_value = cash * req.position_size_pct
                    shares = int(position_value / price)
                    if shares > 0 and cash >= shares * price:
                        cost = shares * price
                        commission = cost * req.commission_pct
                        cash -= cost + commission
                        positions[ticker] = {
                            "shares": shares,
                            "entry_price": price,
                            "entry_date": date_str,
                        }
                        trades.append(
                            BacktestTrade(
                                date=date_str,
                                ticker=ticker,
                                side="BUY",
                                price=round(price, 2),
                                quantity=shares,
                            )
                        )

                elif signal == SignalType.SELL and ticker in positions:
                    pos = positions[ticker]
                    revenue = pos["shares"] * price
                    commission = revenue * req.commission_pct
                    pnl = revenue - (pos["shares"] * pos["entry_price"]) - commission
                    cash += revenue - commission
                    trades.append(
                        BacktestTrade(
                            date=date_str,
                            ticker=ticker,
                            side="SELL",
                            price=round(price, 2),
                            quantity=pos["shares"],
                            pnl=round(pnl, 2),
                        )
                    )
                    del positions[ticker]

            equity = cash
            for ticker, pos in positions.items():
                if ticker in prices.columns and not pd.isna(prices[ticker].iloc[i]):
                    equity += pos["shares"] * float(prices[ticker].iloc[i])

            daily_ret = (equity - prev_equity) / prev_equity if prev_equity > 0 else 0
            daily_returns.append(daily_ret)
            prev_equity = equity
            equity_curve.append({"date": date_str, "equity": round(equity, 2)})

        # Metrics
        rets = np.array(daily_returns)
        final_equity = prev_equity
        total_return = (final_equity - req.initial_capital) / req.initial_capital
        days = len(rets)
        ann_return = (1 + total_return) ** (252 / max(1, days)) - 1

        rf_daily = 0.05 / 252
        excess = rets - rf_daily
        sharpe = (
            float((excess.mean() / excess.std()) * np.sqrt(252))
            if excess.std() > 0
            else 0
        )
        downside = rets[rets < 0]
        sortino = (
            float((excess.mean() / downside.std()) * np.sqrt(252))
            if len(downside) > 0 and downside.std() > 0
            else 0
        )

        cum = np.cumprod(1 + rets)
        peak = np.maximum.accumulate(cum)
        max_dd = float(((cum - peak) / peak).min()) if len(cum) > 0 else 0

        sell_trades = [t for t in trades if t.side == "SELL"]
        wins = [t for t in sell_trades if t.pnl > 0]
        losses = [t for t in sell_trades if t.pnl <= 0]
        win_rate = len(wins) / len(sell_trades) if sell_trades else 0
        avg_win = float(np.mean([t.pnl for t in wins])) if wins else 0
        avg_loss = float(np.mean([t.pnl for t in losses])) if losses else 0
        gross_profit = sum(t.pnl for t in wins) if wins else 0
        gross_loss = abs(sum(t.pnl for t in losses)) if losses else 1
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0

        bench = prices[mkt.BENCHMARK].dropna()
        bench_ret = (
            float(bench.iloc[-1] / bench.iloc[warmup] - 1) if len(bench) > warmup else 0
        )

        monthly = {}
        for ec in equity_curve:
            month = ec["date"][:7]
            if month not in monthly:
                monthly[month] = {"start": ec["equity"]}
            monthly[month]["end"] = ec["equity"]
        monthly_returns = [
            {"month": m, "return": round((v["end"] - v["start"]) / v["start"], 4)}
            for m, v in monthly.items()
            if v["start"] > 0
        ]

        step = max(1, len(equity_curve) // 300)
        sampled = equity_curve[::step]
        if equity_curve and sampled[-1] != equity_curve[-1]:
            sampled.append(equity_curve[-1])

        return BacktestResult(
            strategy=req.strategy.value,
            total_return=round(total_return, 4),
            annualized_return=round(ann_return, 4),
            sharpe_ratio=round(sharpe, 4),
            sortino_ratio=round(sortino, 4),
            max_drawdown=round(max_dd, 4),
            win_rate=round(win_rate, 4),
            total_trades=len(trades),
            avg_win=round(avg_win, 2),
            avg_loss=round(avg_loss, 2),
            profit_factor=round(profit_factor, 4),
            equity_curve=sampled,
            trades=trades[-100:],
            monthly_returns=monthly_returns,
            benchmark_return=round(bench_ret, 4),
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Default Watchlist
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DEFAULT_WATCHLIST = [
    "AAPL",
    "MSFT",
    "GOOGL",
    "AMZN",
    "NVDA",
    "META",
    "TSLA",
    "JPM",
    "V",
    "JNJ",
    "XOM",
    "PG",
    "HD",
    "BAC",
    "GS",
]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  API Endpoints
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "portfolio_equity": portfolio.total_equity,
    }


# ── Signals ──


@app.post("/api/v1/signals/scan", response_model=list[Signal])
async def scan_signals(request: ScanRequest):
    signals = []
    for ticker in request.tickers:
        try:
            ohlcv = mkt.fetch_ohlcv(ticker, 120)
            sig = SignalEngine.generate(ticker, ohlcv["Close"], request.strategy)
            signals.append(sig)
        except Exception as e:
            logger.warning(f"Signal failed for {ticker}: {e}")
    return sorted(signals, key=lambda s: abs(s.strength), reverse=True)


@app.get("/api/v1/signals/watchlist", response_model=list[WatchlistSignal])
async def watchlist_signals(strategy: StrategyName = StrategyName.COMBINED):
    results = []
    for ticker in DEFAULT_WATCHLIST:
        try:
            ohlcv = mkt.fetch_ohlcv(ticker, 120)
            close = ohlcv["Close"]
            info = mkt.get_ticker_info(ticker)
            sig = SignalEngine.generate(ticker, close, strategy)

            rsi_val = float(TA.rsi(close).iloc[-1]) if len(close) > 14 else None
            _, _, hist = TA.macd(close)
            macd_h = (
                float(hist.iloc[-1])
                if len(hist) > 26 and not np.isnan(hist.iloc[-1])
                else None
            )
            _, _, _, pct_b = TA.bollinger_bands(close)
            bb_pos = (
                float(pct_b.iloc[-1])
                if len(pct_b) > 20 and not np.isnan(pct_b.iloc[-1])
                else None
            )

            price = float(close.iloc[-1])
            prev = float(close.iloc[-2]) if len(close) > 1 else price

            results.append(
                WatchlistSignal(
                    ticker=ticker,
                    name=info["name"],
                    price=round(price, 2),
                    change_pct=round((price - prev) / prev, 4) if prev != 0 else 0,
                    sector=info["sector"],
                    signal=sig.signal,
                    strength=sig.strength,
                    strategy=sig.strategy,
                    reason=sig.reason,
                    rsi=round(rsi_val, 2)
                    if rsi_val and not np.isnan(rsi_val)
                    else None,
                    macd_histogram=round(macd_h, 4) if macd_h else None,
                    bb_position=round(bb_pos, 3) if bb_pos else None,
                )
            )
        except Exception as e:
            logger.warning(f"Watchlist failed for {ticker}: {e}")

    return sorted(results, key=lambda r: abs(r.strength), reverse=True)


@app.get("/api/v1/signals/detail/{ticker}")
async def signal_detail(ticker: str, strategy: StrategyName = StrategyName.COMBINED):
    ohlcv = mkt.fetch_ohlcv(ticker, 200)
    close = ohlcv["Close"]
    info = mkt.get_ticker_info(ticker)

    strategies_detail = {}
    for strat in [
        StrategyName.MA_CROSSOVER,
        StrategyName.RSI_REVERSION,
        StrategyName.BOLLINGER_BREAKOUT,
        StrategyName.MACD_MOMENTUM,
    ]:
        sig = SignalEngine.generate(ticker, close, strat)
        strategies_detail[strat.value] = sig.model_dump()

    combined = SignalEngine.generate(ticker, close, StrategyName.COMBINED)
    price_history = [
        {
            "date": d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d),
            "close": round(float(v), 2),
        }
        for d, v in close.tail(120).items()
    ]

    sma_20 = TA.sma(close, 20).tail(120)
    sma_50 = TA.sma(close, 50).tail(120)

    return {
        "ticker": ticker,
        "name": info["name"],
        "sector": info["sector"],
        "combined_signal": combined.model_dump(),
        "strategies": strategies_detail,
        "price_history": price_history,
        "sma_data": {
            "sma_20": [round(float(v), 2) if not np.isnan(v) else None for v in sma_20],
            "sma_50": [round(float(v), 2) if not np.isnan(v) else None for v in sma_50],
        },
    }


# ── Trading ──


@app.post("/api/v1/trade/order", response_model=Order)
async def place_order(order: OrderRequest):
    try:
        ohlcv = mkt.fetch_ohlcv(order.ticker, 5)
        price = float(ohlcv["Close"].iloc[-1])
        info = mkt.get_ticker_info(order.ticker)
        return portfolio.execute_order(order, price, info["sector"])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/trade/signal-trade")
async def trade_on_signal(
    ticker: str, strategy: StrategyName = StrategyName.COMBINED, shares: int = 0
):
    ohlcv = mkt.fetch_ohlcv(ticker, 120)
    close = ohlcv["Close"]
    price = float(close.iloc[-1])
    info = mkt.get_ticker_info(ticker)
    sig = SignalEngine.generate(ticker, close, strategy)

    if sig.signal == SignalType.HOLD:
        return {"message": "No actionable signal", "signal": sig.model_dump()}

    if shares <= 0:
        shares = max(1, int(portfolio.total_equity * 0.10 / price))

    if sig.signal == SignalType.BUY:
        order = OrderRequest(
            ticker=ticker, side=OrderSide.BUY, quantity=shares, reason=sig.reason
        )
    else:
        pos = portfolio.positions.get(ticker)
        if pos:
            shares = min(shares, pos["quantity"])
            order = OrderRequest(
                ticker=ticker, side=OrderSide.SELL, quantity=shares, reason=sig.reason
            )
        else:
            return {
                "message": f"SELL signal but no position in {ticker}",
                "signal": sig.model_dump(),
            }

    result = portfolio.execute_order(order, price, info["sector"])
    return {"signal": sig.model_dump(), "order": result.model_dump()}


# ── Portfolio ──


@app.get("/api/v1/portfolio", response_model=PortfolioState)
async def get_portfolio():
    for ticker in list(portfolio.positions.keys()):
        try:
            ohlcv = mkt.fetch_ohlcv(ticker, 5)
            portfolio.positions[ticker]["current_price"] = float(
                ohlcv["Close"].iloc[-1]
            )
        except Exception:
            pass
    return portfolio.get_state()


@app.get("/api/v1/portfolio/orders")
async def get_orders(limit: int = Query(default=50, ge=1, le=200)):
    return {"orders": portfolio.orders[-limit:][::-1]}


@app.post("/api/v1/portfolio/reset")
async def reset_portfolio(initial_cash: float = Query(default=100_000, gt=0)):
    global portfolio
    portfolio = PaperPortfolio(initial_cash=initial_cash)
    return {"message": "Portfolio reset", "cash": initial_cash}


@app.get("/api/v1/portfolio/risk-check")
async def portfolio_risk_summary():
    state = portfolio.get_state()
    sector_weights: dict[str, float] = {}
    for pos in state.positions:
        info = mkt.get_ticker_info(pos.ticker)
        sector_weights[info["sector"]] = (
            sector_weights.get(info["sector"], 0) + pos.weight
        )

    return {
        "total_equity": state.total_equity,
        "cash_pct": round(state.cash / state.total_equity, 4)
        if state.total_equity > 0
        else 1,
        "num_positions": state.num_positions,
        "max_position_weight": round(
            max((p.weight for p in state.positions), default=0), 4
        ),
        "sector_weights": {k: round(v, 4) for k, v in sector_weights.items()},
        "day_pnl": state.day_pnl,
        "total_pnl": state.total_pnl,
        "total_pnl_pct": state.total_pnl_pct,
        "limits": risk_mgr.limits.model_dump(),
    }


# ── Backtesting ──


@app.post("/api/v1/backtest", response_model=BacktestResult)
async def run_backtest(request: BacktestRequest):
    return Backtester.run(request)


# ── Market Data ──


@app.get("/api/v1/market/quote/{ticker}", response_model=QuoteResponse)
async def get_quote(ticker: str):
    try:
        ohlcv = mkt.fetch_ohlcv(ticker, 10)
        info = mkt.get_ticker_info(ticker)
        close = ohlcv["Close"]
        price = float(close.iloc[-1])
        prev = float(close.iloc[-2]) if len(close) > 1 else price

        return QuoteResponse(
            ticker=ticker.upper(),
            name=info["name"],
            price=round(price, 2),
            change=round(price - prev, 2),
            change_pct=round((price - prev) / prev, 4) if prev != 0 else 0,
            volume=int(ohlcv["Volume"].iloc[-1]) if "Volume" in ohlcv.columns else 0,
            market_cap=info.get("market_cap", 0),
            sector=info["sector"],
            pe_ratio=info.get("pe_ratio"),
            dividend_yield=info.get("dividend_yield"),
            fifty_two_week_high=info.get("fifty_two_week_high"),
            fifty_two_week_low=info.get("fifty_two_week_low"),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/api/v1/market/history/{ticker}")
async def get_history(ticker: str, days: int = Query(default=120, ge=5, le=1260)):
    prices = mkt.fetch_prices([ticker], days)
    if ticker not in prices.columns:
        raise HTTPException(status_code=404, detail=f"No data for {ticker}")
    series = prices[ticker].dropna()
    return {
        "ticker": ticker.upper(),
        "prices": [
            {
                "date": d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d),
                "close": round(float(v), 2),
            }
            for d, v in series.items()
        ],
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
