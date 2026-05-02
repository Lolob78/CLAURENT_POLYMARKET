# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CLAURENT Polymarket is a multi-LLM paper trading agent for Polymarket prediction markets. It is **100% paper/simulation mode** — `PAPER_MODE=true` is a hard safety constraint that must never be disabled. The system runs a LangGraph debate pipeline where three agents (analyst → onchain → judge) collaboratively evaluate prediction market opportunities and execute simulated trades when edge ≥ 10%.

## Commands

```bash
# Install dependencies
poetry install

# Run the 24/7 paper trading bot (starts Streamlit dashboard on http://localhost:8501)
poetry run python scripts/run_24_7_paper_bot.py

# Run the 90-day backtest (note: script lives at repo root, not in scripts/)
poetry run python backtest_90_days.py

# Run tests
poetry run pytest tests/test_risk_engine.py -v

# Run a single test
poetry run pytest tests/test_risk_engine.py::TestRiskEngine::test_close_paper_trade_winning -v

# Lint / format
poetry run ruff check .
poetry run black .
```

Docker alternative:
```bash
docker-compose up --build
```

## Architecture

### Data Flow

```
Gamma API → active markets → [analyze_single_market]
                                  ├── scrape_news_market (Playwright → X.com)
                                  ├── query_dune_mcp (onchain context)
                                  └── debate_graph.ainvoke()
                                        ├── analyst_node  (Grok: news sentiment)
                                        ├── onchain_node  (stub: neutral)
                                        └── judge_node    (Grok: JSON verdict)
                                              └── AgentOutput (edge, side, prob, confidence)
                                                    └── paper_execute() → RiskEngine
```

### Key Modules

- **`src/agents/debate_graph.py`** — The active LangGraph pipeline. Async, uses `aiohttp` to call xAI Grok directly. The `DebateState` dict flows through `analyst → onchain → judge`. The judge node outputs `AgentOutput` (a Pydantic model with `edge`, `side`, `prob_true_yes`, `confidence`, `rationale`).

- **`src/risk/engine.py`** — `RiskEngine` tracks capital ($3000 default), open positions, equity curve, and PnL. `can_trade(edge)` enforces three guards: minimum edge (10%), max concurrent positions (3), and max drawdown (15%). Trade size is hardcoded at $50. A module-level singleton `risk = RiskEngine()` is imported everywhere.

- **`src/config.py`** — Pydantic `Settings` loaded from `.env`. All risk parameters (`edge_min`, `max_drawdown`, etc.) come from here. `src/config_validation.py` runs a fail-fast check at startup.

- **`src/clients/gamma.py`** — Fetches active markets from Polymarket's public Gamma API (no auth needed). Filters by volume ≥ 50k and liquidity > 20k.

- **`src/clients/clob.py`** — **Currently mocked**: `get_live_price()` always returns `0.5`. The real `py_clob_client` code is commented out. Restore when moving to live pricing.

- **`src/ingestion/dune_mcp.py`** — Posts to `DUNE_MCP_URL/query` with a `condition_id`. Returns neutral string on failure. Requires `DUNE_MCP_URL` and `DUNE_API_KEY` in `.env` (not listed in `Settings` class — accessed via `hasattr` guard).

- **`src/utils/persistence.py`** — `TradesPersistence` saves/loads trades as append-only JSON and exports CSV. Module-level singleton `persistence`. Trades write to `data/trades.json`, positions to `data/positions.json`.

- **`src/utils/logger.py`** — Configures `structlog` at import time. Use `get_logger("module_name")` and call with keyword args: `logger.info("event_name", key=value)`.

### Multiple debate_graph Versions

Several versions exist but only `debate_graph.py` is imported by the running code:
- `debate_graph.py` — Active (async, aiohttp, Grok)
- `debate_graph4.py` — Sync version with direct `requests` calls to Grok
- `debate_graph3.py` — Alternate version
- `debate_graph - Sauve.py` — Backup/archive

### Entry Points

- **`scripts/run_24_7_paper_bot.py`** — 24/7 loop cycling every ~40 seconds. Analyzes up to 10 markets per cycle in parallel via `asyncio.gather`. Starts the Streamlit dashboard in a daemon thread.

- **`backtest_90_days.py`** (repo root) — Iterates through up to 300 markets sequentially, immediately resolves each trade using `prob_true_yes > 0.55` as a simulated outcome, exports results to `data/backtest_90j_results.csv`.

## Environment Variables

Copy `.env.example` to `.env`. Required variables:

```
GROK_API_KEY=          # xAI Grok (used by the active debate_graph)
ANTHROPIC_API_KEY=     # Claude (config references it, not yet wired to graph)
OPENAI_API_KEY=        # GPT (config references it, not yet wired to graph)
DUNE_MCP_URL=          # Dune MCP endpoint
DUNE_API_KEY=          # Dune API key
PAPER_MODE=true        # Must remain true
EDGE_MIN=0.10
MAX_OPEN_POSITIONS=3
MAX_DRAWDOWN=0.15
```

`DUNE_MCP_URL` and `DUNE_API_KEY` are not declared in the `Settings` class — `dune_mcp.py` accesses them via `settings.dune_mcp_url` (pydantic will raise) or `hasattr` guard. This is a known gap.

## Planned Improvements (Phase 2)

The codebase has explicit TODOs for: async refactor with `httpx`, WebSocket live prices (replacing the mocked CLOB), SQLite persistence, retry logic, and health checks. Phase 3 targets caching and parallel analysis.
