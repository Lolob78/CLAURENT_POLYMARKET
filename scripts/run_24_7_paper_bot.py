import asyncio
import threading
import time
from datetime import datetime
import structlog

from src.config import settings
from src.clients.gamma import get_active_markets
from src.clients.clob import get_live_price
from src.agents.debate_graph import debate_graph
from src.ingestion.news_scraper import scrape_news_market
from src.ingestion.dune_mcp import query_dune_mcp
from src.execution.paper_executor import paper_execute
from src.risk.engine import risk
from src.dashboard.streamlit_app import run_dashboard
from src.clients.price_manager import price_manager

logger = structlog.get_logger()


async def analyze_single_market(market: dict):
    """Analyse un marché avec tout le pipeline async"""
    try:
        token_id = market.get("clob_token_id") or market.get("clob_token_ids", [None])[0]
        price = await get_live_price(token_id)
        market["price"] = price

        news_task = asyncio.create_task(scrape_news_market(market["question"]))
        onchain_task = asyncio.create_task(asyncio.to_thread(query_dune_mcp, market.get("condition_id", "")))

        news = await news_task
        onchain = await onchain_task

        initial_state = {
            "market": market,
            "news_context": news,
            "onchain_context": onchain
        }

        result = await debate_graph.ainvoke(initial_state)

        if result.get("result") and result["result"].edge >= settings.edge_min:
            await paper_execute(market, result["result"])

        status = risk.get_status()
        logger.info("market_processed",
                    question=market["question"][:60],
                    edge=result["result"].edge if result.get("result") else 0.0,
                    capital=status["capital"],
                    open_positions=status["open_positions"])

    except Exception as e:
        logger.error("market_analysis_error", market=market.get("question", "unknown"), error=str(e))


async def main_24_7_loop():
    """Boucle principale 24/7"""
    logger.info("BOT_STARTED",
                mode="paper",
                edge_min=settings.edge_min,
                risk_per_trade=settings.risk_per_trade)

    while True:
        try:
            markets = get_active_markets(min_volume=50000)[:10]
            tasks = [analyze_single_market(m) for m in markets]
            await asyncio.gather(*tasks, return_exceptions=True)

            if int(time.time()) % 300 == 0:
                status = risk.get_status()
                logger.info("periodic_status",
                            capital=status["capital"],
                            open_pos=status["open_positions"],
                            max_dd=status["max_dd"])

        except Exception as e:
            logger.error("main_loop_error", error=str(e))
            await asyncio.sleep(60)

        await asyncio.sleep(40)


def start_dashboard():
    try:
        run_dashboard()
    except Exception as e:
        logger.error("dashboard_error", error=str(e))


async def main():
    """Point d'entrée principal avec gestion du PriceManager."""
    await price_manager.start()
    try:
        dashboard_thread = threading.Thread(target=start_dashboard, daemon=True)
        dashboard_thread.start()

        print("=" * 60)
        print("  CLAUAURENT 24/7 PAPER TRADING BOT STARTED")
        print("  Dashboard: http://localhost:8501")
        print("=" * 60)

        await main_24_7_loop()
    except KeyboardInterrupt:
        logger.info("BOT_STOPPED")
    except Exception as e:
        logger.critical("fatal_error", error=str(e))
    finally:
        await price_manager.stop()


if __name__ == "__main__":
    asyncio.run(main())
