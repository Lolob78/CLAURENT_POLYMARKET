from src.config import settings
from datetime import datetime

class RiskEngine:
    def __init__(self, initial_capital: float = 3000.0):
        self.capital = initial_capital
        self.equity_curve = [initial_capital]
        self.open_positions = []
        self.trades = []

    def can_trade(self, edge: float) -> bool:
        if edge < settings.edge_min:
            return False
        if len(self.open_positions) >= settings.max_open_positions:
            return False
        current_dd = (self.equity_curve[-1] - max(self.equity_curve)) / max(self.equity_curve) if self.equity_curve else 0
        if current_dd < -settings.max_drawdown:
            return False
        return True

    def execute_paper_trade(self, market: dict, side: str, edge: float, price: float):
        size = 50.0  # taille fixe conservatrice pour paper (ajuste plus tard)
        entry = {
            "market_id": market.get("condition_id"),
            "question": market.get("question", "")[:80],
            "side": side,
            "size": size,
            "entry_price": price,
            "entry_time": datetime.utcnow().isoformat(),
            "edge": edge
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
        self.trades.append({"time": datetime.utcnow().isoformat(), "action": "close", "pnl": round(pnl, 2)})

    def get_status(self):
        dd = (self.equity_curve[-1] - max(self.equity_curve)) / max(self.equity_curve) * 100 if self.equity_curve else 0
        return {
            "capital": round(self.capital, 2),
            "open_positions": len(self.open_positions),
            "equity_curve": self.equity_curve[-20:],
            "max_dd": round(dd, 1)
        }
risk = RiskEngine()