# from py_clob_client_v2.client import ClobClient
# from py_clob_client_v2.clob_types import BookParams
from src.config import settings

def get_clob_client():
    """Mock: pas besoin du CLOB pour MVP"""
    return None  # ← Retourne None au lieu de créer un client

async def get_live_price(token_id: str):
    """Prix live mock"""
    return 0.5  # ← Utilise prix neutre




# def get_clob_client():
#     """Client CLOB read-only (Level 0) pour paper trading"""
#     client = ClobClient(host="https://clob.polymarket.com")  # L0 = no auth pour prices/book
#     return client

# async def get_live_price(token_id: str):
#     """Prix live (fallback synchrone pour simplicité)"""
#     try:
#         client = get_clob_client()
#         price = client.get_price(token_id)
#         return float(price)
#     except:
#         return 0.5  # fallback neutre