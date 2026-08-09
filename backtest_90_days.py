"""Backtest 90 jours avec analyse parallèle et gestion d'erreurs robuste.
Compatibilité : Août 2026 (MarketAnalyzer, WebSocket CLOB)
"""
import asyncio
import csv
from datetime import datetime
from typing import List

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False

from src.config import settings
from src.config_validation import validate_config
from src.risk.engine import risk
from src.utils.logger import get_logger
from src.utils.persistence import persistence
from src.clients.price_manager import price_manager
from src.analyzers.market_analyzer import market_analyzer

logger = get_logger("backtest")


async def run_backtest_90_days(num_markets: int = 300):
    """Backtest réaliste sur 90 jours - Paper mode avec analyse parallèle."""
    risk.__init__(initial_capital=3000.0)

    logger.info(
        "BACKTEST_START",
        capital_initial=3000,
        edge_min=settings.edge_min,
        markets_to_test=num_markets,
        max_concurrent=market_analyzer.max_concurrent
    )

    start_time = datetime.utcnow()

    # Analyser les marchés en parallèle
    analyses = await market_analyzer.analyze_markets(limit=num_markets, min_volume=50000)
    total_trades = 0
    capital_start = risk.capital
    successful_analyses = len([a for a in analyses if a.success])

    print("=" * 60)
    print("  Lancement Backtest 90 jours (Parallèle)")
    print("=" * 60)

    for i, analysis in enumerate(analyses):
        try:
            if not analysis.success:
                logger.warning("skipping_failed_analysis", market_id=analysis.market.get("id"), error=analysis.error)
                continue

            if analysis.edge >= settings.edge_min:
                market = analysis.market
                risk.execute_paper_trade(
                    market,
                    analysis.side,
                    analysis.edge,
                    analysis.price
                )

                # Résolution simulée (prob_true_yes > 0.55 = YES gagne)
                resolution_price = 1.0 if getattr(analysis, "prob_true_yes", 0.5) > 0.55 else 0.0
                if risk.open_positions:
                    risk.close_paper_trade(risk.open_positions[-1], resolution_price)

                total_trades += 1
                print(
                    f"  [{i+1}/{len(analyses)}] TRADE | "
                    f"Edge {analysis.edge:+.1%} | {analysis.side} | "
                    f"Latency: {analysis.latency:.2f}s | "
                    f"{analysis.rationale[:50]}..."
                )

        except Exception as e:
            logger.error(
                "backtest_trade_error",
                market=analysis.market.get("question", "unknown")[:50],
                error=str(e)
            )
            continue

    duration = (datetime.utcnow() - start_time).total_seconds()
    return_pct = round((risk.capital - capital_start) / capital_start * 100, 2)

    print("=" * 60)
    print("  BACKTEST TERMINÉ")
    print("=" * 60)

    logger.info(
        "BACKTEST_RESULTS",
        capital_final=round(risk.capital, 2),
        return_pct=return_pct,
        total_trades=total_trades,
        successful_analyses=successful_analyses,
        max_drawdown=risk.get_status()["max_dd"],
        duration_seconds=round(duration, 1),
        avg_latency=sum(a.latency for a in analyses) / len(analyses) if analyses else 0
    )

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
    print(f"Analyses réussies : {successful_analyses}/{len(analyses)}")
    print(f"Latence moyenne : {sum(a.latency for a in analyses) / len(analyses):.2f}s" if analyses else "N/A")
    print(f"Max Drawdown   : {risk.get_status()['max_dd']}%")
    print(f"CSV exporté    : {csv_path}")
    print(f"Durée          : {duration/60:.1f} minutes")

    return {
        "capital_final": risk.capital,
        "return_pct": return_pct,
        "trades": total_trades,
        "max_dd": risk.get_status()["max_dd"],
        "avg_latency": sum(a.latency for a in analyses) / len(analyses) if analyses else 0
    }


async def main():
    """Point d'entrée principal."""
    await price_manager.start()
    try:
        return await run_backtest_90_days(num_markets=300)
    finally:
        await price_manager.stop()
        market_analyzer.clear_cache()


if __name__ == "__main__":
    asyncio.run(main())
