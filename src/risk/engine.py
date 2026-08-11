from src.config import settings
from datetime import datetime

class RiskEngine:
    def __init__(self, initial_capital: float = 3000.0):
        self.capital = initial_capital
        self.equity_curve = [initial_capital]
        self.open_positions = []
        self.trades = []
        # Seuils de sortie (configurables via settings/env)
        self.take_profit = settings.take_profit      # gain % pour clôturer
        self.stop_loss = settings.stop_loss          # perte % pour clôturer
        self.max_hold_minutes = settings.max_hold_minutes

    def can_trade(self, edge: float, price: float | None = None, side: str | None = None) -> bool:
        """Vérifie si un trade est autorisé.

        Garde-fous :
        1. edge >= edge_min
        2. prix d'entrée dans [min_entry_price, max_entry_price] (filtre strict)
           → exclut les paris quasi-certains (0.0015) où le LLM a 99% de
           chances d'avoir tort contre le marché
        3. ratio gain potentiel / risque >= min_reward_ratio
           → on achète le token à `price`, il vaut 1$ si gagné :
             gain = (1 - price), risque = price → ratio = (1-price)/price
        4. max positions ouvertes
        5. max drawdown
        """
        if edge < settings.edge_min:
            return False
        if price is not None:
            if not (settings.min_entry_price <= price <= settings.max_entry_price):
                return False
            ratio = (1.0 - price) / price
            if ratio < settings.min_reward_ratio:
                return False
        if len(self.open_positions) >= settings.max_open_positions:
            return False
        current_dd = (self.equity_curve[-1] - max(self.equity_curve)) / max(self.equity_curve) if self.equity_curve else 0
        if current_dd < -settings.max_drawdown:
            return False
        return True

    def execute_paper_trade(self, market: dict, side: str, edge: float, price: float):
        size = 50.0  # taille fixe conservatrice pour paper (ajuste plus tard)
        # Déduplication : refuser si le même marché est déjà en position
        # (les analyses parallèles peuvent traiter le même marché plusieurs fois)
        market_id = market.get("condition_id") or market.get("id")
        # ID numérique (le plus fiable pour interroger la résolution)
        market_num_id = market.get("id") or market.get("market_id")
        for pos in self.open_positions:
            if pos["market_id"] == market_id:
                return False
        # Token du côté acheté (pour suivre le prix de sortie) : clobTokenIds = [YES, NO]
        token_ids = market.get("clob_token_ids") or market.get("clobTokenIds") or []
        token_id = token_ids[0] if side == "YES" and token_ids else \
                   (token_ids[1] if side == "NO" and len(token_ids) > 1 else None)
        entry = {
            "market_id": market_id,
            "market_num_id": market_num_id,
            "question": market.get("question", "")[:80],
            "side": side,
            "size": size,
            "entry_price": price,
            "entry_time": datetime.utcnow().isoformat(),
            "edge": edge,
            "token_id": token_id
        }
        self.open_positions.append(entry)
        self.trades.append({"time": entry["entry_time"], "action": "open", "pnl": 0})

    def close_paper_trade(self, position: dict, exit_price: float):
        # On ACHÈTE le token (YES ou NO) à entry_price, il vaut exit_price à la résolution.
        # PnL identique pour les deux côtés : size × (exit - entry)
        pnl = position["size"] * (exit_price - position["entry_price"])
        self.capital += pnl
        self.equity_curve.append(self.capital)
        if position in self.open_positions:
            self.open_positions.remove(position)
        self.trades.append({"time": datetime.utcnow().isoformat(), "action": "close",
                            "pnl": round(pnl, 2), "reason": position.get("close_reason", "resolve"),
                            "exit_price": round(exit_price, 4)})
        return pnl

    def manage_positions(self, current_prices: dict) -> list:
        """Évalue les positions ouvertes et retourne celles à clôturer.

        `current_prices` : {market_id (condition_id): prix_actuel_du_token}.
        Une position est clôturée si :
        - TP atteint : prix >= entry × (1 + take_profit)
        - SL atteint : prix <= entry × (1 - stop_loss)
        - timeout : temps de détention > max_hold_minutes
        Retourne la liste des positions à fermer (l'appelant fait la résolution).
        """
        to_close = []
        now = datetime.utcnow()
        for pos in list(self.open_positions):
            mid = current_prices.get(pos["market_id"])
            if mid is None:
                continue  # pas de prix → on garde
            # PnL en % sur le token
            change = (mid - pos["entry_price"]) / pos["entry_price"]
            reason = None
            if change >= self.take_profit:
                reason = "take_profit"
            elif change <= -self.stop_loss:
                reason = "stop_loss"
            else:
                # Vérifier le timeout de détention
                try:
                    entered = datetime.fromisoformat(pos["entry_time"])
                    if (now - entered).total_seconds() / 60 > self.max_hold_minutes:
                        reason = "timeout"
                except (ValueError, TypeError):
                    pass
            if reason:
                to_close.append({**pos, "close_reason": reason, "current_price": mid,
                                 "change_pct": change})
        return to_close

    def get_status(self):
        dd = (self.equity_curve[-1] - max(self.equity_curve)) / max(self.equity_curve) * 100 if self.equity_curve else 0
        return {
            "capital": round(self.capital, 2),
            "open_positions": len(self.open_positions),
            "equity_curve": self.equity_curve[-20:],
            "max_dd": round(dd, 1)
        }
risk = RiskEngine()