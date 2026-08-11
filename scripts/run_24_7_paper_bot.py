"""
Bot 24/7 avec analyse parallèle et gestion des erreurs.
Compatibilité : Août 2026 (MarketAnalyzer, WebSocket CLOB)
"""

import asyncio
import threading
import time
from datetime import datetime
import structlog
from typing import List

from src.config import settings
from src.risk.engine import risk
from src.dashboard.streamlit_app import run_dashboard
from src.clients.price_manager import price_manager
from src.analyzers.market_analyzer import market_analyzer
from src.execution.paper_executor import paper_execute
from src.utils.budget import budget, BudgetExceeded

logger = structlog.get_logger()


async def analyze_markets_batch():
    """
    Analyse un batch de marchés en parallèle.
    Retourne le nombre de trades exécutés.
    """
    try:
        analyses = await market_analyzer.analyze_markets(limit=20, min_volume=50000)
        trades_executed = 0

        for analysis in analyses:
            if not analysis.success:
                continue

            if analysis.edge >= settings.edge_min:
                success = await paper_execute(analysis.market, analysis)
                if success:
                    trades_executed += 1

        return trades_executed

    except BudgetExceeded:
        raise  # propager l'arrêt budget à la boucle principale
    except Exception as e:
        logger.error("batch_analysis_error", error=str(e))
        return 0


async def main_24_7_loop():
    """Boucle principale 24/7 avec analyse parallèle."""
    logger.info(
        "BOT_STARTED",
        mode="paper",
        edge_min=settings.edge_min,
        max_concurrent=market_analyzer.max_concurrent
    )

    while True:
        try:
            start_time = time.time()
            trades_executed = await analyze_markets_batch()
            duration = time.time() - start_time

            if int(time.time()) % 300 == 0:
                status = risk.get_status()
                logger.info(
                    "periodic_status",
                    capital=status["capital"],
                    open_positions=status["open_positions"],
                    max_dd=status["max_dd"],
                    trades_executed=trades_executed,
                    batch_duration=f"{duration:.2f}s"
                )

            sleep_time = max(0, 30.0 - duration)
            await asyncio.sleep(sleep_time)

        except KeyboardInterrupt:
            logger.info("BOT_STOPPED_BY_USER")
            break
        except BudgetExceeded as e:
            # Budget LLM épuisé → arrêt propre (pas de relance)
            logger.critical("BUDGET_EXCEEDED_SHUTDOWN", message=str(e),
                            status=budget.status())
            print("\n🚫 BUDGET LLM DÉPASSÉ — arrêt propre du bot.")
            print(f"   {budget.status()}")
            break
        except Exception as e:
            logger.error("main_loop_error", error=str(e))
            await asyncio.sleep(60)


def start_dashboard():
    try:
        run_dashboard()
    except Exception as e:
        logger.error("dashboard_error", error=str(e))


async def main():
    """Point d'entrée principal."""
    await price_manager.start()
    try:
        dashboard_thread = threading.Thread(target=start_dashboard, daemon=True)
        dashboard_thread.start()

        print("=" * 60)
        print("  CLAUAURENT 24/7 PAPER TRADING BOT STARTED")
        print("  Dashboard: http://localhost:8501")
        print("  Mode: Parallèle (10 marchés en //)")
        print("=" * 60)

        await main_24_7_loop()

    except KeyboardInterrupt:
        logger.info("BOT_STOPPED")
    except Exception as e:
        logger.critical("fatal_error", error=str(e))
    finally:
        await price_manager.stop()
        market_analyzer.clear_cache()


if __name__ == "__main__":
    asyncio.run(main())
