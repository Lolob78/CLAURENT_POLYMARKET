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


def get_market_resolution(market_id):
    """Interroge Gamma sur un marché résolu. Retourne (exit_yes, exit_no) ou None.

    `market_id` : l'ID numérique du marché Polymarket (ex: 3244603), le plus
    fiable pour l'interroger. Si le marché est closed, outcomePrices (string
    JSON) = [prix_yes, prix_no] selon le résultat réel. None si pas résolu.
    """
    if not market_id:
        return None
    try:
        import requests
        import json as _json
        r = requests.get(
            f"https://gamma-api.polymarket.com/markets/{market_id}",
            timeout=10, headers={"User-Agent": "CLAURENT-bot/1.0"}
        )
        if r.status_code != 200:
            return None
        m = r.json()
        if not m or not m.get("closed"):
            return None
        prices = m.get("outcomePrices")
        if not prices:
            return None
        # outcomePrices peut être une string JSON '["1","0"]' ou une liste
        if isinstance(prices, str):
            try:
                prices = _json.loads(prices)
            except _json.JSONDecodeError:
                return None
        if not isinstance(prices, list) or len(prices) < 2:
            return None
        try:
            return float(prices[0]), float(prices[1])
        except (TypeError, ValueError):
            return None
    except Exception:
        return None


async def manage_open_positions():
    """Ferme les positions ouvertes qui atteignent TP, SL, timeout OU résolution.

    Ordre de priorité :
    1. Résolution réelle du marché (Gamma closed + outcomePrices) → valeur 1/0
    2. TP/SL : gain/perte sur le token
    3. Timeout de détention
    """
    if not risk.open_positions:
        return 0

    # 1. Vérifier la résolution réelle des marchés détenus
    closed_count = 0
    resolved_ids = {}
    for pos in risk.open_positions:
        mid = pos.get("market_num_id") or pos.get("market_id")
        if not mid:
            continue
        try:
            resolved = await asyncio.to_thread(get_market_resolution, mid)
            if resolved is not None:
                resolved_ids[pos["market_id"]] = resolved  # (exit_price_yes, exit_price_no)
        except Exception as e:
            logger.error("resolve_check_error", market=mid, error=str(e))

    # 2. Clôturer les marchés résolus à leur valeur réelle
    for pos in list(risk.open_positions):
        res = resolved_ids.get(pos["market_id"])
        if res is None:
            continue
        exit_yes, exit_no = res
        exit_price = exit_yes if pos["side"] == "YES" else exit_no
        pnl = risk.close_paper_trade(pos, exit_price)
        closed_count += 1
        logger.info("paper_position_resolved", side=pos["side"], exit_price=exit_price,
                    pnl=round(pnl, 2), market=pos.get("question", "")[:50])
        print(f"PAPER RESOLVE | {pos['side']} @ {exit_price:.2f} | PnL {pnl:+.2f}$ | {pos.get('question','')[:40]}")

    # 3. TP/SL/timeout sur les positions encore ouvertes
    prices = {}
    for pos in risk.open_positions:
        token_id = pos.get("token_id") or pos.get("market_id")
        if not token_id:
            continue
        try:
            pd = await price_manager.get_price(token_id)
            if pd:
                prices[pos["market_id"]] = pd.mid
        except Exception as e:
            logger.error("manage_price_error", token=token_id, error=str(e))

    for pos in risk.manage_positions(prices):
        try:
            exit_price = pos["current_price"]
            pnl = risk.close_paper_trade(pos, exit_price)
            closed_count += 1
            logger.info("paper_position_closed", side=pos["side"],
                        reason=pos["close_reason"], change_pct=round(pos["change_pct"] * 100, 1),
                        pnl=round(pnl, 2),
                        market=pos.get("question", "")[:50])
            print(f"PAPER CLOSE | {pos['close_reason']} | {pos['side']} | "
                  f"{pos['change_pct']:+.1%} | PnL {pnl:+.2f}$ | {pos.get('question','')[:40]}")
        except Exception as e:
            logger.error("manage_close_error", error=str(e))
    return closed_count


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
            # 1. Gérer les sorties des positions ouvertes (TP/SL/timeout)
            closed = await manage_open_positions()
            # 2. Analyser de nouveaux marchés (libère de la place si des closes ont eu lieu)
            trades_executed = await analyze_markets_batch()
            duration = time.time() - start_time

            if int(time.time()) % 300 == 0 or closed:
                status = risk.get_status()
                logger.info(
                    "periodic_status",
                    capital=status["capital"],
                    open_positions=status["open_positions"],
                    max_dd=status["max_dd"],
                    trades_executed=trades_executed,
                    positions_closed=closed,
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
