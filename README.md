Markdown# CLAUAURENT Polymarket Paper Trading Agent

Agent multi-LLM pour arbitrage sur Polymarket (100% paper mode).
# 1. Créer un virtualenv
python -m venv venv

# 2. Activer (Windows)
venv\Scripts\activate
# Ou (Linux/Mac)
source venv/bin/activate

# 3. Installer les dépendances
pip install -r requirements.txt

# 4. Lancer le backtest
python scripts/backtest_90_days.py


## Lancement local
poetry install
poetry run python scripts/run_24_7_paper_bot.py

Dashboard : http://localhost:8501

Backtest 90j :
poetry run python scripts/backtest_90_days.py
**📌 Contenu du projet :**
- **471 lignes de code Python** réparties entre 12 modules
- **Configuration complète** (pyproject.toml, .env.example, Docker)
- **3 scripts exécutables** : bot 24/7, backtest 90j, scan de marchés

**🤖 Architecture IA :**
- **Débat multi-LLM** (LangGraph) : 3 agents (analyst, onchain, judge)
- **4 LLMs supportés** : CLAU-4, Claude Sonnet, GPT-5 Mini, Anthropic
- **Ingestion parallèle** : scraping news + données onchain (Dune MCP)

**💰 Trading :**
- **Paper trading 100% simulé** avec gestion des risques
- **Moteur de risque** : max drawdown, positions max, edge minimum
- **CLOB client** pour les prix live Polymarket
- **Risk engine** : tracking capital, equity curve, PnL

**📊 Dashboard :**
- Streamlit app intégrée pour visualiser l'activité en temps réel
- Equity curve, positions ouvertes, historique des trades

**🐳 Containerisation :**
- Dockerfile complet avec support Playwright (scraping)
- docker-compose.yml pour orchestration
