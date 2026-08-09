"""Backtest 90 jours avec persistence et gestion d'erreurs robuste."""
import asyncio
import csv
from datetime import datetime

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False

from src.config import settings
from src.config_validation import validate_config
from src.clients.gamma import get_active_markets
from src.clients.clob import get_live_price
from src.agents.debate_graph import debate_graph
from src.ingestion.news_scraper import scrape_news_market
from src.ingestion.dune_mcp import query_dune_mcp
from src.risk.engine import risk
from src.utils.logger import get_logger
from src.utils.persistence import persistence
from src.clients.price_manager import price_manager

logger = get_logger("backtest")


async def run_backtest_90_days(num_markets: int = 500):
    """Backtest réaliste sur 90 jours - Paper mode"""
    risk.__init__(initial_capital=3000.0)

    logger.info("BACKTEST_START",
                capital_initial=3000,
                edge_min=settings.edge_min,
                markets_to_test=num_markets)

    start_time = datetime.utcnow()
    all_markets = get_active_markets(min_volume=50000, limit=300)
    test_markets = all_markets[:num_markets]

    total_trades = 0
    capital_start = risk.capital
    successful_analyses = 0

    print("=" * 60)
    print("  Lancement Backtest 90 jours")
    print("=" * 60)

    for i, market in enumerate(test_markets):
        try:
            print(f"[{i+1}/{len(test_markets)}] {market['question'][:70]}...")

            news = await scrape_news_market(market["question"])
            onchain = await asyncio.to_thread(query_dune_mcp, market.get("condition_id", ""))

            initial_state = {
                "market": market,
                "news_context": news,
                "onchain_context": onchain
            }

            result = await debate_graph.ainvoke(initial_state)

            if not result or not result.get("result"):
                continue

            agent_output = result["result"]
            edge = agent_output.edge
            successful_analyses += 1

            if edge >= settings.edge_min:
                token_id = market.get("clob_token_id") or (market.get("clob_token_ids", [None])[0])
                price = await get_live_price(token_id)

                risk.execute_paper_trade(market, agent_output.side, edge, price)

                resolution_price = 1.0 if agent_output.prob_true_yes > 0.55 else 0.0
                risk.close_paper_trade(risk.open_positions[-1], resolution_price)

                total_trades += 1
                print(f"  -> TRADE | Edge {edge:+.1%} | {agent_output.side} | {agent_output.rationale[:60]}")

        except Exception as e:
            logger.error("backtest_market_error",
                        market=market.get("question", "unknown")[:50],
                        error=str(e))
            continue

    duration = (datetime.utcnow() - start_time).total_seconds()
    return_pct = round((risk.capital - capital_start) / capital_start * 100, 2)

    print("=" * 60)
    print("  BACKTEST TERMINE")
    print("=" * 60)

    logger.info("BACKTEST_RESULTS",
                capital_final=round(risk.capital, 2),
                return_pct=return_pct,
                total_trades=total_trades,
                successful_analyses=successful_analyses,
                max_drawdown=risk.get_status()["max_dd"],
                duration_seconds=round(duration, 1))

    # Export CSV
    csv_path = "data/backtest_90j_results.csv"
    if HAS_PANDAS:
        pd.DataFrame(risk.trades).to_csv(csv_path, index=False)
    elif risk.trades:
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=risk.trades[0].keys())
            writer.writeheader()
            writer.writerows(risk.trades)

    print(f"Capital final  : ${risk.capital:.2f} ({return_pct:+.2f}%)")
    print(f"Trades         : {total_trades}")
    print(f"Max Drawdown   : {risk.get_status()['max_dd']}%")
    print(f"CSV exporté    : {csv_path}")
    print(f"Durée          : {duration/60:.1f} minutes")

    return {
        "capital_final": risk.capital,
        "return_pct": return_pct,
        "trades": total_trades,
        "max_dd": risk.get_status()["max_dd"]
    }


async def main():
    """Point d'entrée principal avec gestion du PriceManager."""
    await price_manager.start()
    try:
        return await run_backtest_90_days(num_markets=300)
    finally:
        await price_manager.stop()


if __name__ == "__main__":
    asyncio.run(main())
