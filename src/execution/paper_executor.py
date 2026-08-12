"""Exécution des paper trades avec logging et gestion erreurs."""
from src.risk.engine import risk
from src.config import settings
from src.clients.clob import get_live_price
from src.clients.price_manager import price_manager
from src.utils.logger import get_logger

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
        # Token du côté acheté : clob_token_ids = [YES, NO]
        token_ids = market.get("clob_token_ids") or market.get("clobTokenIds") or []
        buy_token = token_ids[0] if result.side == "YES" and token_ids else \
                    (token_ids[1] if result.side == "NO" and len(token_ids) > 1 else None)
        # Prix RÉEL du côté acheté uniquement. Rejeter si aucun prix réel :
        # JAMAIS utiliser le prix du token YES pour un trade NO (incohérent),
        # JAMAIS trader à un prix fictif.
        price = None
        if buy_token:
            pd = await price_manager.get_price(buy_token)
            if pd and 0 < pd.mid < 1:
                price = pd.mid
        if price is None:
            # Dernier recours : prix réel direct via CLOB (pas de fallback fictif)
            price = await get_live_price(buy_token)
        if price is None or not (0 < price < 1):
            logger.info("paper_execute_no_price",
                        side=result.side, market=market.get("question", "")[:60])
            return False
        # Garde-fous : filtre prix strict + ratio récompense/risque + cooldown
        market_id = market.get("condition_id") or market.get("id")
        if not risk.can_trade(result.edge, price, result.side, market_id=market_id):
            logger.info("paper_execute_risk_filter",
                        edge=result.edge, price=price, side=result.side,
                        market=market.get("question", "")[:60])
            return False
        # Stocker le token du côté acheté pour le suivi de sortie
        if not risk.execute_paper_trade(market, result.side, result.edge, price):
            logger.info("paper_execute_duplicate", market=market.get("question", "")[:60])
            return False

        logger.info(
            "paper_trade_opened",
            side=result.side,
            edge=result.edge,
            price=price,
            market=market.get("question", "")[:60],
        )
        print(f"PAPER TRADE OPEN | {result.side} | Edge {result.edge:+.1%} | {result.rationale[:100]}...")
        return True

    except Exception as e:
        logger.error("paper_execute_error", error=str(e), market=market.get("question", ""))
        print(f"Erreur exécution trade: {e}")
        return False
