# 🚀 CLAUAURENT - Setup & Démarrage

## Installation

### Prérequis
- Python 3.11+
- Poetry
- Docker (optionnel)

### Setup local
```bash
# 1. Copier le projet
cp -r CLAURENT-polymarket-agent ~/projects/

# 2. Créer l'env
cd CLAURENT-polymarket-agent
poetry install

# 3. Configurer
cp .env.example .env
# Éditer .env avec tes clés API
```

## Lancement

### Backtest (prioritaire)
```bash
# Lancer le backtest 90 jours
poetry run python scripts/backtest_90_days.py

# Les résultats sont sauvés dans data/backtest_90j_results.csv
```

### Bot 24/7
```bash
poetry run python scripts/run_24_7_paper_bot.py

# Dashboard disponible sur http://localhost:8501
```

### Tests
```bash
poetry run pytest tests/test_risk_engine.py -v
```

## Structure

```
src/
├── config.py              # Configuration
├── config_validation.py   # Validation au startup
├── agents/               # Débat multi-LLM
├── clients/              # APIs (Gamma, CLOB)
├── ingestion/            # News scraper, Dune MCP
├── risk/                 # Money management
├── execution/            # Paper trading executor
├── dashboard/            # Streamlit app
└── utils/                # Logging, persistence
```

## Améliorations Phase 1 (cette version)

✅ **Bug fixes**
- Imports manquants corrigés
- run_dashboard() créée
- Gestion erreurs uniformisée

✅ **Persistence**
- Sauvegarde trades en JSON (résistant aux crashes)
- Export CSV final

✅ **Tests**
- test_risk_engine.py (8 tests unitaires)

✅ **Logging**
- structlog configuré
- Logs structurés (JSON)

## Points clés pour le backtest

1. **Edge minimum** : 10% (configurable dans .env)
2. **Capital initial** : $3000 (simule un compte small)
3. **Max drawdown** : 15%
4. **Max positions ouvertes** : 3
5. **Taille par trade** : $50 (fixed pour MVP)

## Prochaines étapes (Phase 2)

- [ ] Async refactor (httpx + WebSocket pour prix live)
- [ ] SQLite persistence (positions, equity curve)
- [ ] Health checks + monitoring
- [ ] Caching des données (news, onchain)
- [ ] Retry logic + rate limiting

