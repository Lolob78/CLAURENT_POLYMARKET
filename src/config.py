from dataclasses import dataclass
from dotenv import load_dotenv
import os

load_dotenv()

@dataclass
class Settings:
    paper_mode: bool = True
    edge_min: float = 0.10
    risk_per_trade: float = 0.005
    max_open_positions: int = 3
    max_drawdown: float = 0.15
    min_entry_price: float = 0.10   # filtre strict : prix d'entrée minimum
    max_entry_price: float = 0.90   # filtre strict : prix d'entrée maximum
    min_reward_ratio: float = 1.5   # ratio gain potentiel / risque minimal
    rag_persist_dir: str = "./data/rag_db"
    default_llm_analyst: str = "claude-4-sonnet-2026-04"
    default_llm_onchain: str = "CLAU-4"
    default_llm_quant: str = "gpt-5-mini"
    default_llm_judge: str = "claude-4-sonnet-2026-04"
    dune_mcp_url: str = "https://mcp.dune.com"
    dune_api_key: str = ""
    clob_ws_url: str = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
    gamma_api_url: str = "https://gamma-api.polymarket.com"
    clob_api_url: str = "https://clob.polymarket.com"

    def __post_init__(self):
        self.paper_mode = os.getenv("PAPER_MODE", "true").lower() == "true"
        self.edge_min = float(os.getenv("EDGE_MIN", str(self.edge_min)))
        self.risk_per_trade = float(os.getenv("RISK_PER_TRADE", str(self.risk_per_trade)))
        self.max_open_positions = int(os.getenv("MAX_OPEN_POSITIONS", str(self.max_open_positions)))
        self.max_drawdown = float(os.getenv("MAX_DRAWDOWN", str(self.max_drawdown)))
        self.min_entry_price = float(os.getenv("MIN_ENTRY_PRICE", str(self.min_entry_price)))
        self.max_entry_price = float(os.getenv("MAX_ENTRY_PRICE", str(self.max_entry_price)))
        self.min_reward_ratio = float(os.getenv("MIN_REWARD_RATIO", str(self.min_reward_ratio)))
        self.rag_persist_dir = os.getenv("RAG_PERSIST_DIR", self.rag_persist_dir)
        self.dune_mcp_url = os.getenv("DUNE_MCP_URL", self.dune_mcp_url)
        self.dune_api_key = os.getenv("DUNE_API_KEY", self.dune_api_key)
        self.clob_ws_url = os.getenv("CLOB_WS_URL", self.clob_ws_url)
        self.gamma_api_url = os.getenv("GAMMA_API_URL", self.gamma_api_url)
        self.clob_api_url = os.getenv("CLOB_API_URL", self.clob_api_url)

settings = Settings()
