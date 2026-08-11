"""Budget LLM — compteur de coût avec kill switch.

Sécurité : une boucle ou un timeout qui déraille ne doit pas faire grimper
la facture OpenRouter sans limite. Ce module :
1. Compte le coût RÉEL de chaque appel (tokens du champ `usage`)
2. Accumule sur le budget total
3. Quand le budget est dépassé → lève BudgetExceeded → le bot s'arrête proprement

Le prix est calculé sur les prix OpenRouter de DeepSeek V4 Flash :
- input  : $0.08 / 1M tokens (cache miss), $0.02 (cache hit)
- output : $0.18 / 1M tokens

Configurable via env LLM_BUDGET_USD (défaut 8.0 = ~8€).
"""
import asyncio
import os
import json
from pathlib import Path
from typing import Dict

from src.utils.logger import get_logger

logger = get_logger("budget")

# Fichier de persistance du budget (survit aux redémarrages)
BUDGET_FILE = Path("./data/llm_budget.json")

# Prix par million de tokens (USD) — DeepSeek V4 Flash via OpenRouter
PRICE_INPUT = 0.08
PRICE_INPUT_CACHED = 0.02
PRICE_OUTPUT = 0.18


class BudgetExceeded(Exception):
    """Levée quand le budget LLM est dépassé — déclenche l'arrêt propre."""


class BudgetTracker:
    def __init__(self, budget_usd: float | None = None):
        self.budget_usd = budget_usd if budget_usd is not None \
            else float(os.getenv("LLM_BUDGET_USD", "8.0"))
        self.spent_usd = 0.0
        self.tokens_in = 0
        self.tokens_out = 0
        self.calls = 0
        self._lock = asyncio.Lock()
        self._load()  # reprend le compteur persistant si présent

    def _load(self) -> None:
        """Recharge le compteur depuis le disque (résilience aux redémarrages)."""
        try:
            if BUDGET_FILE.exists():
                d = json.loads(BUDGET_FILE.read_text())
                self.spent_usd = float(d.get("spent_usd", 0))
                self.tokens_in = int(d.get("tokens_in", 0))
                self.tokens_out = int(d.get("tokens_out", 0))
                self.calls = int(d.get("calls", 0))
                if self.spent_usd > 0:
                    logger.warning("budget_restored", spent_usd=round(self.spent_usd, 3),
                                   calls=self.calls)
        except Exception:
            pass

    def _save(self) -> None:
        """Persiste le compteur sur disque."""
        try:
            BUDGET_FILE.parent.mkdir(exist_ok=True)
            BUDGET_FILE.write_text(json.dumps({
                "spent_usd": self.spent_usd,
                "tokens_in": self.tokens_in,
                "tokens_out": self.tokens_out,
                "calls": self.calls,
            }))
        except Exception:
            pass

    def record(self, usage: Dict) -> None:
        """Enregistre le coût d'un appel depuis le champ `usage` de la réponse."""
        try:
            prompt_tokens = int(usage.get("prompt_tokens") or 0)
            completion_tokens = int(usage.get("completion_tokens") or 0)
            cost = (
                prompt_tokens / 1_000_000 * PRICE_INPUT
                + completion_tokens / 1_000_000 * PRICE_OUTPUT
            )
            self.spent_usd += cost
            self.tokens_in += prompt_tokens
            self.tokens_out += completion_tokens
            self.calls += 1
            self._save()
            logger.info("llm_cost", call=self.calls, tokens_in=prompt_tokens,
                        tokens_out=completion_tokens, cost_usd=round(cost, 5),
                        total_usd=round(self.spent_usd, 5))
        except (TypeError, ValueError):
            pass  # usage mal formé → on ne bloque pas

    def check(self) -> None:
        """Lève BudgetExceeded si le budget est dépassé."""
        if self.spent_usd >= self.budget_usd:
            logger.error("budget_exceeded", spent_usd=round(self.spent_usd, 3),
                         budget_usd=self.budget_usd)
            raise BudgetExceeded(
                f"Budget LLM dépassé : ${self.spent_usd:.2f} >= ${self.budget_usd:.2f}"
            )

    def status(self) -> str:
        return (f"budget: ${self.spent_usd:.3f}/${self.budget_usd:.2f} "
                f"({self.calls} appels, {self.tokens_in:,} in / {self.tokens_out:,} out)")


budget = BudgetTracker()
