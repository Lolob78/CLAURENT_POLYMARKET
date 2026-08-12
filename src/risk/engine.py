from src.config import settings
from src.utils.logger import get_logger
from datetime import datetime
import json
from pathlib import Path

logger = get_logger("risk_engine")

class RiskEngine:
    def __init__(self, initial_capital: float = 3000.0, restore_state: bool = True):
        self.capital = initial_capital
        self.equity_curve = [initial_capital]
        self.open_positions = []
        self.trades = []
        # Seuils de sortie (configurables via settings/env)
        self.take_profit = settings.take_profit      # gain % pour clôturer
        self.stop_loss = settings.stop_loss          # perte % pour clôturer
        self.max_hold_minutes = settings.max_hold_minutes
        self.cooldown_minutes = settings.cooldown_minutes  # interdiction de ré-ouvrir un marché après clôture
        # {market_id: timestamp fin de cooldown}
        self._cooldowns: dict = {}
        self._state_file = Path("./data/risk_state.json")
        if restore_state:
            self._load_state()

    def _load_state(self):
        """Recharge le state (capital, positions, cooldowns) après un crash/redémarrage."""
        try:
            if self._state_file.exists():
                with open(self._state_file, 'r') as f:
                    state = json.load(f)
                self.capital = float(state.get("capital", self.capital))
                self.open_positions = state.get("open_positions", [])
                # Restaurer equity_curve (au minimum le capital courant)
                self.equity_curve = state.get("equity_curve") or [self.capital]
                self._cooldowns = {k: float(v) for k, v in state.get("cooldowns", {}).items()}
                self.trades = state.get("trades", [])
                if self.open_positions:
                    logger.info("risk_state_restored", capital=self.capital,
                                positions=len(self.open_positions),
                                cooldowns=len(self._cooldowns))
        except Exception as e:
            logger.error("risk_state_load_error", error=str(e))

    def _save_state(self):
        """Persiste le state à chaque changement (résilience anti-crash)."""
        try:
            self._state_file.parent.mkdir(exist_ok=True)
            state = {
                "capital": self.capital,
                "open_positions": self.open_positions,
                "equity_curve": self.equity_curve[-100:],
                "cooldowns": {k: v for k, v in self._cooldowns.items()
                              if v > datetime.utcnow().timestamp()},
                "trades": self.trades[-200:],
                "saved_at": datetime.utcnow().isoformat(),
            }
            with open(self._state_file, 'w') as f:
                json.dump(state, f, indent=2, default=str)
        except Exception as e:
            logger.error("risk_state_save_error", error=str(e))

    def can_trade(self, edge: float, price: float | None = None, side: str | None = None,
                  market_id: str | None = None) -> bool:
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
        6. cooldown : marché non ré-ouvert après une clôture récente
        """
        if edge < settings.edge_min:
            return False
        if market_id and self.in_cooldown(market_id):
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
        self._save_state()
        return True

    def close_paper_trade(self, position: dict, exit_price: float):
        # On ACHÈTE le token (YES ou NO) à entry_price, il vaut exit_price à la résolution.
        # PnL identique pour les deux côtés : size × (exit - entry)
        pnl = position["size"] * (exit_price - position["entry_price"])
        self.capital += pnl
        self.equity_curve.append(self.capital)
        if position in self.open_positions:
            self.open_positions.remove(position)
        # Cooldown anti-ré-ouverture (sauf si résolution réelle gagnante : pas de ré-ouv)
        if position.get("close_reason") in ("stop_loss", "timeout"):
            self.start_cooldown(position.get("market_id", ""), reason=position["close_reason"])
        self.trades.append({"time": datetime.utcnow().isoformat(), "action": "close",
                            "pnl": round(pnl, 2), "reason": position.get("close_reason", "resolve"),
                            "exit_price": round(exit_price, 4)})
        self._save_state()
        return pnl

    def in_cooldown(self, market_id: str) -> bool:
        """True si le marché est encore en cooldown (ré-ouverture interdite)."""
        end = self._cooldowns.get(market_id)
        if end is None:
            return False
        if datetime.utcnow().timestamp() > end:
            self._cooldowns.pop(market_id, None)  # cooldown expiré → nettoyage
            return False
        return True

    def start_cooldown(self, market_id: str, reason: str = "close") -> None:
        """Met un marché en cooldown après clôture (empêche la boucle de ré-ouverture)."""
        if not market_id:
            return
        self._cooldowns[market_id] = datetime.utcnow().timestamp() + self.cooldown_minutes * 60
        logger.info("market_cooldown_started", market_id=market_id,
                    minutes=self.cooldown_minutes, reason=reason)
        self._save_state()

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