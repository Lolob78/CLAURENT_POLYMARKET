import requests
from src.config import settings

def query_dune_mcp(condition_id: str, natural_query: str = "whale flows and user intent"):
    """Dune MCP - requête naturelle onchain"""
    if not condition_id:
        return "No condition_id provided - neutral onchain context"
    try:
        resp = requests.post(
            f"{settings.dune_mcp_url}/query",
            json={"condition_id": condition_id, "natural_query": natural_query},
            headers={"Authorization": f"Bearer {settings.dune_api_key}" if hasattr(settings, 'dune_api_key') else ""},
            timeout=10
        )
        if resp.status_code == 200:
            return resp.json().get("result", "Onchain data retrieved")
        return "Dune MCP returned error"
    except:
        return "Dune MCP unavailable - neutral context"