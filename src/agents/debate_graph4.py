"""Débat multi-LLM avec appels directs xAI."""
from langgraph.graph import StateGraph, END
from src.config import settings
from src.agents.structured_output import AgentOutput
import requests
import os
import json

class DebateState(dict):
    market: dict
    news_context: str = ""
    onchain_context: str = ""
    result: AgentOutput | None = None

def call_grok(prompt: str) -> str:
    """Appel direct à l'API xAI Grok."""
    grok_key = os.getenv("GROK_API_KEY")
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {grok_key}"
    }
    
    data = {
        "model": "grok-4",
        "input": prompt
    }
    
    try:
        response = requests.post(
            "https://api.x.ai/v1/responses",
            headers=headers,
            json=data,
            timeout=30
        )
        response.raise_for_status()
        result = response.json()
        
        # Extraire le texte de la bonne place
        text = result['output'][0]['content'][0]['text']
        return text
        
    except Exception as e:
        print(f"❌ Erreur Grok: {e}")
        return ""

def analyst_node(state: DebateState):
    """Analyse news avec Grok."""
    question = state['market']['question']
    prompt = f"Analyse brièvement le sentiment pour: {question}\nRéponds en 1-2 phrases."
    
    state["news_context"] = call_grok(prompt)
    return state


def onchain_node(state: DebateState):
    """Contexte onchain."""
    state["onchain_context"] = "Onchain activity neutral"
    return state


def judge_node(state: DebateState):
    """Jugement final avec Grok."""
    prompt = f"""Pour ce marché: {state['market']['question']}
News: {state.get('news_context', '')}
Prix: {state['market'].get('price', 0.5)}

Retourne UNIQUEMENT un JSON valide:
{{
  "prob_true_yes": 0.XX,
  "confidence": XX,
  "edge": 0.XX,
  "rationale": "texte court",
  "side": "YES ou NO"
}}"""
    
    response_text = call_grok(prompt)
    
    try:
        # Extraire JSON de la réponse
        data = json.loads(response_text)
        state["result"] = AgentOutput(**data)
    except:
        state["result"] = AgentOutput(
            prob_true_yes=0.5, 
            confidence=50, 
            edge=0.0, 
            rationale="Parse error", 
            side="YES"
        )
    return state


def build_debate_graph():
    workflow = StateGraph(DebateState)
    workflow.add_node("analyst", analyst_node)
    workflow.add_node("onchain", onchain_node)
    workflow.add_node("judge", judge_node)
    workflow.set_entry_point("analyst")
    workflow.add_edge("analyst", "onchain")
    workflow.add_edge("onchain", "judge")
    workflow.add_edge("judge", END)
    return workflow.compile()

debate_graph = build_debate_graph()