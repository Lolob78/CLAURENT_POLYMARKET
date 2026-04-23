from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    paper_mode: bool = True
    edge_min: float = 0.10
    risk_per_trade: float = 0.005
    max_open_positions: int = 3
    max_drawdown: float = 0.15
    rag_persist_dir: str = "./data/rag_db"
    
    default_llm_analyst: str = "claude-4-sonnet-2026-04"
    default_llm_onchain: str = "CLAU-4"
    default_llm_quant: str = "gpt-5-mini"
    default_llm_judge: str = "claude-4-sonnet-2026-04"

settings = Settings()