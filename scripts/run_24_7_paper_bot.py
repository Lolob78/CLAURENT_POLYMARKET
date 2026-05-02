import asyncio
import threading
import time
from datetime import datetime
import structlog
from rich.console import Console

from src.config import settings
from src.clients.gamma import get_active_markets
from src.clients.clob import get_live_price
from src.agents.debate_graph import debate_graph
from src.ingestion.news_scraper import scrape_news_market
from src.ingestion.dune_mcp import query_dune_mcp
from src.execution.paper_executor import paper_execute
from src.risk.engine import risk
from src.dashboard.streamlit_app import run_dashboard  # fonction qui lance Streamlit

console = Console()
logger = structlog.get_logger()

async def analyze_single_market(market: dict):
    """Analyse un marché avec tout le pipeline async"""
    try:
        # Prix live via WebSocket / fallback
        token_id = market.get("clob_token_id") or market.get("token_id")
        price = await get_live_price(token_id)
        market["price"] = price

        # Ingestion parallèle
        news_task = asyncio.create_task(scrape_news_market(market["question"]))
        onchain_task = asyncio.create_task(asyncio.to_thread(query_dune_mcp, market.get("condition_id", "")))

        news = await news_task
        onchain = await onchain_task

        # Débat multi-LLM
        initial_state = {
            "market": market,
            "news_context": news,
            "onchain_context": onchain
        }

        result = await debate_graph.ainvoke(initial_state)

        # Exécution paper si edge suffisant
        if result.get("result") and result["result"].edge >= settings.edge_min:
            await paper_execute(market, result["result"])

        # Log status périodique
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
    logger.info("🚀 CLAUAURENT 24/7 PAPER BOT STARTED", 
                mode="small_bankroll", 
                edge_min=settings.edge_min,
                risk_per_trade=settings.risk_per_trade)

    while True:
        try:
            markets = get_active_markets(min_volume=50000)[:10]  # max 10 pour stabilité

            # Analyse parallèle
            tasks = [analyze_single_market(m) for m in markets]
            await asyncio.gather(*tasks, return_exceptions=True)

            # Status toutes les 5 minutes
            if int(time.time()) % 300 == 0:
                status = risk.get_status()
                logger.info("periodic_status", 
                            capital=status["capital"], 
                            open_pos=status["open_positions"], 
                            max_dd=status["max_dd"])

        except Exception as e:
            logger.error("main_loop_error", error=str(e))
            await asyncio.sleep(60)  # backoff en cas d'erreur

        await asyncio.sleep(40)  # boucle toutes les ~40 secondes

def start_dashboard():
    """Lance Streamlit en thread séparé"""
    try:
        run_dashboard()
    except Exception as e:
        logger.error("dashboard_error", error=str(e))

if __name__ == "__main__":
    # Dashboard en background
    dashboard_thread = threading.Thread(target=start_dashboard, daemon=True)
    dashboard_thread.start()

    console.rule("[bold green]CLAUAURENT 24/7 PAPER TRADING BOT STARTED[/bold green]")
    console.log("Dashboard disponible sur http://localhost:8501")

    # Lancement boucle principale
    try:
        asyncio.run(main_24_7_loop())
    except KeyboardInterrupt:
        logger.info("🛑 Bot arrêté par l'utilisateur")
    except Exception as e:
        logger.critical("fatal_error", error=str(e))