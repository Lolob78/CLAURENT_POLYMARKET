"""Tests unitaires du RiskEngine."""
import pytest
from src.risk.engine import RiskEngine
from src.config import settings


class TestRiskEngine:
    """Tests du moteur de gestion des risques."""

    def setup_method(self):
        """Reset avant chaque test."""
        self.engine = RiskEngine(initial_capital=1000.0)

    def test_initial_capital(self):
        """Le capital initial est correct."""
        assert self.engine.capital == 1000.0
        assert len(self.engine.equity_curve) == 1
        assert self.engine.equity_curve[0] == 1000.0

    def test_can_trade_with_sufficient_edge(self):
        """Permet un trade si l'edge est suffisant."""
        assert self.engine.can_trade(edge=0.15) is True

    def test_can_trade_with_low_edge(self):
        """Refuse un trade si l'edge est trop faible."""
        assert self.engine.can_trade(edge=0.05) is False

    def test_max_open_positions(self):
        """Refuse un trade si trop de positions ouvertes."""
        # Ouvrir le max de positions
        for i in range(settings.max_open_positions):
            market = {"condition_id": f"market_{i}", "question": f"Q{i}"}
            self.engine.execute_paper_trade(market, "YES", 0.15, 0.5)

        # Impossible d'en ouvrir une de plus
        assert self.engine.can_trade(edge=0.20) is False

    def test_execute_paper_trade(self):
        """L'exécution d'un trade enregistre la position."""
        market = {"condition_id": "cond_123", "question": "Test market"}
        self.engine.execute_paper_trade(market, "YES", 0.15, 0.60)

        assert len(self.engine.open_positions) == 1
        pos = self.engine.open_positions[0]
        assert pos["side"] == "YES"
        assert pos["entry_price"] == 0.60
        assert pos["edge"] == 0.15

    def test_close_paper_trade_winning(self):
        """Fermer un trade gagnant augmente le capital."""
        market = {"condition_id": "cond_123", "question": "Test market"}
        self.engine.execute_paper_trade(market, "YES", 0.15, 0.40)

        # Fermer en gagnant (prix monte à 1.0)
        pos = self.engine.open_positions[0]
        self.engine.close_paper_trade(pos, exit_price=1.0)

        # PnL = 50 * (1.0 - 0.4) = 30
        assert self.engine.capital == 1030.0
        assert len(self.engine.open_positions) == 0

    def test_close_paper_trade_losing(self):
        """Fermer un trade perdant diminue le capital."""
        market = {"condition_id": "cond_123", "question": "Test market"}
        self.engine.execute_paper_trade(market, "YES", 0.15, 0.60)

        # Fermer en perdant (prix baisse à 0.0)
        pos = self.engine.open_positions[0]
        self.engine.close_paper_trade(pos, exit_price=0.0)

        # PnL = 50 * (0.0 - 0.6) = -30
        assert self.engine.capital == 970.0
        assert len(self.engine.open_positions) == 0

    def test_drawdown_calculation(self):
        """Le drawdown se calcule correctement."""
        # Ouvrir et fermer un trade perdant
        market = {"condition_id": "cond_123", "question": "Test"}
        self.engine.execute_paper_trade(market, "YES", 0.15, 0.70)
        self.engine.close_paper_trade(self.engine.open_positions[0], 0.0)

        status = self.engine.get_status()
        # DD = (970 - 1000) / 1000 * 100 = -3%
        assert status["max_dd"] < 0  # DD négatif (drawdown)

    def test_status_report(self):
        """get_status() retourne un rapport valide."""
        status = self.engine.get_status()

        assert "capital" in status
        assert "open_positions" in status
        assert "equity_curve" in status
        assert "max_dd" in status
        assert status["capital"] == 1000.0
        assert status["open_positions"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
