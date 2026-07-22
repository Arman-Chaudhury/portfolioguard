# PortfolioGuard — Quantitative Trading System

A full-stack quantitative trading platform built with **FastAPI** and **React**. Generates real-time trading signals from technical analysis, executes paper trades with risk controls, and backtests strategies against historical market data.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     React Dashboard                          │
│  Signal Scanner │ Portfolio │ Trade Terminal │ Backtester     │
└───────────────────────┬─────────────────────────────────────┘
                        │ REST API
┌───────────────────────┴─────────────────────────────────────┐
│                    FastAPI Backend                            │
│                                                              │
│  ┌──────────────┐  ┌───────────────┐  ┌─────────────────┐  │
│  │ Signal Engine │  │ Paper Trading │  │ Risk Manager    │  │
│  │ 4 strategies  │  │ Positions     │  │ Pre-trade checks│  │
│  │ + combined    │  │ Orders        │  │ Limits          │  │
│  └──────┬───────┘  │ P&L tracking  │  │ Circuit breakers│  │
│         │          └───────────────┘  └─────────────────┘  │
│  ┌──────┴───────┐  ┌───────────────┐                        │
│  │ Technical    │  │ Backtester    │                        │
│  │ Analysis     │  │ Historical    │                        │
│  │ RSI, MACD,   │  │ replay with   │                        │
│  │ BB, SMA, ATR │  │ costs         │                        │
│  └──────────────┘  └───────────────┘                        │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │          Yahoo Finance (Market Data + Metadata)       │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## Features

### Signal Generation Engine
Five strategy modes that analyze live market data and produce BUY / SELL / HOLD signals with strength scores from -1.0 to +1.0:

| Strategy | Method | Best For |
|----------|--------|----------|
| **MA Crossover** | SMA(20) vs SMA(50) crossover detection | Trend following |
| **RSI Reversion** | RSI(14) oversold/overbought zones | Mean reversion |
| **Bollinger Breakout** | %B position within Bollinger Bands | Volatility |
| **MACD Momentum** | MACD histogram crossover and divergence | Momentum |
| **Combined** | Consensus vote across all 4 strategies | Balanced |

### Paper Trading Engine
Simulated brokerage with realistic execution:
- **Position management** — buy, sell, average-up, close positions
- **Commission model** — $0.005/share, $1 minimum
- **P&L tracking** — unrealized per-position, realized on close, daily reset
- **Portfolio state** — equity, cash, weights, buying power

### Risk Manager
Pre-trade risk checks that automatically reject dangerous orders:
- **Position size limit** — default 20% max per position
- **Max positions** — default 15 concurrent positions
- **Daily loss circuit breaker** — halts trading after configurable loss
- **Cash availability** — prevents over-leveraging

### Backtesting Engine
Test any strategy against historical data:
- Processes 60+ days of warmup, then trades signals forward
- Applies transaction costs (configurable commission rate)
- Computes Sharpe, Sortino, max drawdown, win rate, profit factor
- Generates equity curve, monthly returns, and full trade log
- Benchmarks against SPY

### Dashboard
Professional trading terminal with four views:
- **Signal Scanner** — live BUY/SELL signals for 15 tickers with RSI, MACD, BB indicators
- **Portfolio** — positions, P&L, order history, account controls
- **Trade** — manual order entry + one-click signal execution
- **Backtest** — strategy configuration, equity curves, performance metrics

---

## Quick Start

### With Docker
```bash
docker compose up --build
# Frontend: http://localhost:3000
# API docs: http://localhost:8000/docs
```

### Without Docker
```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev
```

---

## API Reference

### Signals
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/signals/watchlist` | GET | Signals for 15-ticker watchlist |
| `/api/v1/signals/scan` | POST | Custom ticker list scan |
| `/api/v1/signals/detail/{ticker}` | GET | Deep analysis with all strategies |

### Trading
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/trade/order` | POST | Place a buy/sell order |
| `/api/v1/trade/signal-trade` | POST | Auto-execute based on signal |
| `/api/v1/portfolio` | GET | Current portfolio state |
| `/api/v1/portfolio/orders` | GET | Order history |
| `/api/v1/portfolio/reset` | POST | Reset account |
| `/api/v1/portfolio/risk-check` | GET | Risk assessment |

### Backtesting
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/backtest` | POST | Run a full strategy backtest |

### Market Data
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/market/quote/{ticker}` | GET | Real-time quote |
| `/api/v1/market/history/{ticker}` | GET | Historical prices |

---

## Running Tests

```bash
cd backend
pytest ../tests/ -v
```

---

## Project Structure

```
portfolioguard/
├── backend/
│   ├── main.py              # FastAPI app — all modules in one file
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── PortfolioGuard.jsx   # Trading dashboard
│   │   └── main.jsx
│   ├── index.html
│   ├── package.json
│   └── Dockerfile
├── tests/
│   └── test_trading_system.py
├── docker-compose.yml
└── README.md
```

---

## Configuration

Default risk limits (adjustable via API):

| Parameter | Default | Description |
|-----------|---------|-------------|
| Max position % | 20% | Max single position as % of equity |
| Max positions | 15 | Max concurrent open positions |
| Daily loss limit | $5,000 | Trading halts after this daily loss |
| Commission | $0.005/share | Minimum $1 per order |

Default watchlist: AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA, JPM, V, JNJ, XOM, PG, HD, BAC, GS

---

## Disclaimer

This is a paper trading system for educational and development purposes. It does not execute real trades or connect to any brokerage. Past backtest performance does not indicate future results. Do not use signal outputs as sole investment advice.

---

## Tech Stack

- **Backend**: Python 3.11+, FastAPI, NumPy, Pandas, yfinance
- **Frontend**: React 18, Vite
- **Deployment**: Docker Compose, Nginx reverse proxy
- **Testing**: pytest, httpx
