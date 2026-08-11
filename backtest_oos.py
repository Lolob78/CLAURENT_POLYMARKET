"""Backtest OOS Polymarket — marchés résolus, prix reconstitués depuis les trades.

Honnête :
- Résultat RÉEL (outcomePrices) au lieu d'une simulation
- Le LLM analyse avec le prix au moment T (48h avant résolution), SANS connaître le résultat
- Prix d'entrée = dernier trade avant T (reconstitué via Data API)
"""
import asyncio
import json
import time
import requests
from datetime import datetime, timezone
from typing import List, Dict, Optional

from src.config import settings
from src.risk.engine import RiskEngine
from src.agents.debate_graph import debate_graph
from src.ingestion.news_engine import fetch_news_at
from src.utils.logger import get_logger

logger = get_logger("backtest_oos")

GAMMA = "https://gamma-api.polymarket.com"
DATA = "https://data-api.polymarket.com"
HEADERS = {"User-Agent": "CLAURENT-Polymarket-Bot/1.0"}

# Point T d'entrée : fraction de la durée de vie du marché (milieu de vie)
# Plus robuste que fin - LOOKBACK_HOURS pour les marchés courts (< 48h)
T_FRACTION = 0.5


def get_resolved_markets(min_volume: float = 3000, limit: int = 100) -> List[Dict]:
    """Marchés résolus avec volume, résultat réel (outcomePrices).

    Exclut les marchés FDV crypto (pari 'one day after launch' sans edge
    informationnel pour un LLM) et garde les marchés prédictibles.
    """
    markets = []
    offset = 0
    while len(markets) < limit and offset < 600:
        r = requests.get(f"{GAMMA}/markets",
            params={"closed": "true", "order": "endDate", "ascending": "false",
                    "limit": 100, "offset": offset},
            headers=HEADERS, timeout=20)
        if r.status_code != 200:
            break
        batch = r.json()
        if not batch:
            break
        for m in batch:
            vol = float(m.get("volumeNum", 0) or 0)
            op = m.get("outcomePrices")
            q = m.get("question", "")
            # Exclure les paris crypto purs (FDV one-day, token launch)
            if ("FDV" in q or "one day after launch" in q
                    or "launch a token" in q or "token by " in q):
                continue
            if vol >= min_volume and op and q:
                markets.append(m)
        offset += len(batch)
    return markets[:limit]


def get_trades(condition_id: str, max_trades: int = 200) -> List[Dict]:
    """Trades d'un marché via Data API (pagination)."""
    trades = []
    offset = 0
    while len(trades) < max_trades:
        r = requests.get(f"{DATA}/trades",
            params={"market": condition_id, "limit": 100, "offset": offset},
            headers=HEADERS, timeout=20)
        if r.status_code != 200:
            break
        batch = r.json()
        if not batch:
            break
        trades.extend(batch)
        offset += len(batch)
    return trades[:max_trades]


def price_at_time(trades: List[Dict], outcome: str, t: int) -> Optional[float]:
    """Dernier prix d'un outcome (Yes/No) avant timestamp t."""
    best = None
    for tr in trades:
        if tr.get("outcome", "").lower() == outcome.lower() and tr.get("timestamp", 0) <= t:
            if best is None or tr["timestamp"] > best["timestamp"]:
                best = tr
    return float(best["price"]) if best else None


def whale_context(trades: List[Dict], t: int, window_hours: int = 72,
                  min_usd: float = 2000) -> str:
    """Reconstitue les mouvements de gros wallets autour du point T.

    Agrège les trades (BUY/SELL) par wallet sur la fenêtre [T-72h, T],
    pondérés en USD (size × price). Retourne un résumé des plus gros
    mouvements nets — signal "smart money" que le prix ne montre pas.
    """
    window_start = t - window_hours * 3600
    agg = {}  # wallet -> {buy_usd, sell_usd, buy_yes, sell_yes}
    for tr in trades:
        ts = tr.get("timestamp", 0)
        if not (window_start <= ts <= t):
            continue
        size = float(tr.get("size", 0) or 0)
        price = float(tr.get("price", 0) or 0)
        usd = size * price
        side = tr.get("side", "").upper()
        outcome = tr.get("outcome", "")
        w = agg.setdefault(tr.get("proxyWallet", "?"), {"buy": 0, "sell": 0, "yes_buy": 0, "no_buy": 0})
        if side == "BUY":
            w["buy"] += usd
            if outcome.lower() == "yes":
                w["yes_buy"] += usd
            else:
                w["no_buy"] += usd
        else:
            w["sell"] += usd
    # Top wallets par activité nette
    rows = []
    for w, v in agg.items():
        net = v["buy"] - v["sell"]
        if v["buy"] + v["sell"] >= min_usd:
            rows.append((net, v, w))
    rows.sort(key=lambda x: -abs(x[0]))
    if not rows:
        return "No significant whale activity in window."
    lines = []
    for net, v, w in rows[:3]:
        bias = "YES" if v["yes_buy"] > v["no_buy"] else "NO"
        direction = "accumulation" if net > 0 else "distribution"
        lines.append(
            f"- wallet {w[:8]}…: {direction} net ${abs(net):,.0f} "
            f"(achats ${v['buy']:,.0f}/ventes ${v['sell']:,.0f}), biais {bias}"
        )
    return "\n".join(lines)


async def analyze_market(market: Dict, price_yes: float, price_no: float, t: int,
                         news: str, whale: str) -> Dict:
    """Analyse LLM au moment T — le résultat n'est PAS exposé.

    Le judge reçoit :
    - le prix RÉEL du token YES au moment T (pas le mid, qui serait 0.5)
    - les news de l'ÉPOQUE via GDELT (fenêtre [T-14j, T]) — pas de look-ahead
    - le contexte whale (mouvements de gros wallets dans [T-72h, T])
    """
    state = {
        "market": {
            "question": market["question"],
            "price": price_yes,  # prix réel du token YES au moment T
            "condition_id": market.get("conditionId", ""),
        },
        "news_context": news,
        "onchain_context": whale,
    }
    try:
        result = await asyncio.wait_for(debate_graph.ainvoke(state), timeout=45.0)
        out = result.get("result")
        if out is None:
            return {"success": False, "error": "debate_failed"}
        return {"success": True, "edge": out.edge, "side": out.side,
                "prob": out.prob_true_yes, "confidence": out.confidence,
                "rationale": out.rationale}
    except asyncio.TimeoutError:
        return {"success": False, "error": "timeout"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def resolve(market: Dict, side: str) -> float:
    """Prix de résolution réel pour le côté choisi (1.0 si gagnant, 0.0 sinon)."""
    op = json.loads(market["outcomePrices"]) if isinstance(market["outcomePrices"], str) else market["outcomePrices"]
    # outcomePrices = [prix YES, prix NO] à la résolution → 1.0 = gagnant
    yes_value = float(op[0])
    return yes_value if side == "YES" else (1.0 - yes_value)


async def run_oos_backtest(num_markets: int = 100, min_volume: float = 5000):
    risk = RiskEngine(initial_capital=3000.0)
    markets = get_resolved_markets(min_volume=min_volume, limit=num_markets)
    logger.info("OOS_START", markets=len(markets), edge_min=settings.edge_min,
                t_fraction=T_FRACTION)

    # Phase 1 : préparation séquentielle (trades, prix, news GDELT datées, whale)
    # GDELT impose 1 req/5s → séquentiel est le plus efficace (pas de contention)
    prepared = []
    for m in markets:
        try:
            cond = m.get("conditionId")
            trades = get_trades(cond)
            if not trades:
                continue
            first_ts = min(t["timestamp"] for t in trades)
            last_ts = max(t["timestamp"] for t in trades)
            # Fenêtre de vie réelle du marché : premier → dernier trade
            # (plus fiable que endDate Gamma, souvent erroné)
            t = int(first_ts + (last_ts - first_ts) * T_FRACTION)
            price_yes = price_at_time(trades, "Yes", t)
            price_no = price_at_time(trades, "No", t)
            if price_yes is None or price_no is None:
                logger.warning("price_missing", market_id=cond[:12],
                               yes=price_yes, no=price_no)
                continue
            news = await fetch_news_at(m["question"], t, window_days=7)
            whale = whale_context(trades, t)
            prepared.append({"market": m, "cond": cond, "t": t,
                             "price_yes": price_yes, "price_no": price_no,
                             "news": news, "whale": whale})
            logger.info("oos_prepared", done=len(prepared), market_id=cond[:12],
                        whale=whale[:40])
        except Exception as e:
            logger.error("prepare_error", error=str(e))
    logger.info("OOS_PREPARED", markets_with_data=len(prepared))

    # Phase 2 : analyses LLM en parallèle (5 concurrents — évite la contention OpenRouter)
    sem = asyncio.Semaphore(5)

    async def bounded_analyze(p):
        async with sem:
            return await analyze_market(p["market"], p["price_yes"], p["price_no"],
                                        p["t"], p["news"], p["whale"])

    analyses = await asyncio.gather(*(bounded_analyze(p) for p in prepared))

    total_trades = 0
    wins = 0
    for p, analysis in zip(prepared, analyses):
        try:
            if not analysis["success"]:
                continue
            entry_price = p["price_yes"] if analysis["side"] == "YES" else p["price_no"]
            if analysis["edge"] >= settings.edge_min and risk.can_trade(analysis["edge"], entry_price, analysis["side"]):
                risk.execute_paper_trade(
                    {"condition_id": p["cond"], "question": p["market"]["question"]},
                    analysis["side"], analysis["edge"], entry_price
                )
                exit_price = resolve(p["market"], analysis["side"])
                if risk.open_positions:
                    risk.close_paper_trade(risk.open_positions[-1], exit_price)
                total_trades += 1
                won = (exit_price == 1.0)
                wins += 1 if won else 0
                print(f"  [{total_trades}] {analysis['side']:3s} edge={analysis['edge']:+.0%} "
                      f"entrée={entry_price:.2f} → {'WIN' if won else 'LOSS'} | {p['market']['question'][:45]}")

        except Exception as e:
            logger.error("oos_market_error", market_id=p["cond"][:12], error=str(e))
            continue

    pct = (risk.capital - 3000) / 3000 * 100
    print("=" * 60)
    print("  BACKTEST OOS TERMINÉ")
    print("=" * 60)
    print(f"Marchés analysés  : {len(prepared)}")
    print(f"Trades            : {total_trades} ({wins} wins / {total_trades - wins} losses)")
    print(f"Win rate          : {wins / total_trades:.1%}" if total_trades else "N/A")
    print(f"Capital final     : ${risk.capital:.2f} ({pct:+.2f}%)")
    print(f"Max drawdown      : {risk.get_status()['max_dd']}%")
    return {"trades": total_trades, "wins": wins, "capital": risk.capital, "return_pct": pct}


if __name__ == "__main__":
    import sys
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    asyncio.run(run_oos_backtest(num_markets=n))
