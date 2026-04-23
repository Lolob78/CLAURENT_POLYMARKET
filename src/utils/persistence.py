"""Persistence des trades et state en JSON/CSV."""
import json
from pathlib import Path
from datetime import datetime
import pandas as pd
from typing import List, Dict, Any


class TradesPersistence:
    """Sauvegarde des trades pour éviter de perdre les données en cas de crash."""

    def __init__(self, data_dir: str = "./data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        self.trades_file = self.data_dir / "trades.json"
        self.positions_file = self.data_dir / "positions.json"

    def save_trades(self, trades: List[Dict[str, Any]]):
        """Sauvegarde les trades en JSON (append-only pour résilience)."""
        try:
            # Lire les trades existants
            existing = []
            if self.trades_file.exists():
                with open(self.trades_file, 'r') as f:
                    existing = json.load(f)

            # Fusionner et sauvegarder
            all_trades = existing + [t for t in trades if t not in existing]

            with open(self.trades_file, 'w') as f:
                json.dump(all_trades, f, indent=2, default=str)
        except Exception as e:
            print(f"⚠️ Erreur persistence trades: {e}")

    def save_positions(self, positions: List[Dict[str, Any]]):
        """Sauvegarde les positions ouvertes."""
        try:
            with open(self.positions_file, 'w') as f:
                json.dump(positions, f, indent=2, default=str)
        except Exception as e:
            print(f"⚠️ Erreur persistence positions: {e}")

    def load_trades(self) -> List[Dict[str, Any]]:
        """Charge les trades depuis le fichier."""
        if self.trades_file.exists():
            try:
                with open(self.trades_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"⚠️ Erreur chargement trades: {e}")
                return []
        return []

    def load_positions(self) -> List[Dict[str, Any]]:
        """Charge les positions depuis le fichier."""
        if self.positions_file.exists():
            try:
                with open(self.positions_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"⚠️ Erreur chargement positions: {e}")
                return []
        return []

    def export_to_csv(self, trades: List[Dict[str, Any]], filename: str = "trades.csv"):
        """Exporte les trades en CSV pour analyse."""
        try:
            df = pd.DataFrame(trades)
            csv_path = self.data_dir / filename
            df.to_csv(csv_path, index=False)
            print(f"✅ Trades exportés en {csv_path}")
            return csv_path
        except Exception as e:
            print(f"⚠️ Erreur export CSV: {e}")
            return None


# Instance globale
persistence = TradesPersistence()
