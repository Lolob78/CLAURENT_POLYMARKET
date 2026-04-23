"""Exécution des paper trades avec logging et gestion erreurs."""
from src.risk.engine import risk
from src.config import settings
from src.clients.clob import get_live_price
from src.utils.logger import get_logger
from rich.console import Console

console = Console()
logger = get_logger("paper_executor")


async def paper_execute(market: dict, result):
    """Exécution paper trade avec gestion d'erreurs robuste."""
    if not result:
        logger.debug("paper_execute_skip_no_result", market=market.get("question", ""))
        return False

    if result.edge < settings.edge_min:
        logger.debug("paper_execute_skip_low_edge", edge=result.edge, edge_min=settings.edge_min)
        return False

    try:
        price = await get_live_price(market.get("clob_token_id") or market.get("token_id"))
        risk.execute_paper_trade(market, result.side, result.edge, price)

        logger.info(
            "paper_trade_opened",
            side=result.side,
            edge=result.edge,
            price=price,
            market=market.get("question", "")[:60],
        )
        console.log(f"[bold green]PAPER TRADE OPEN[/] {result.side} | Edge {result.edge:+.1%} | {result.rationale[:100]}...")
        return True

    except Exception as e:
        logger.error("paper_execute_error", error=str(e), market=market.get("question", ""))
        console.log(f"[red]❌ Erreur exécution trade: {e}[/red]")
        return False
