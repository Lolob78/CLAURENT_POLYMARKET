from langgraph.graph import StateGraph, END
from litellm import completion
from src.config import settings
from src.agents.structured_output import AgentOutput
import json

class DebateState(dict):
    market: dict
    news_context: str = ""
    onchain_context: str = ""
    result: AgentOutput | None = None

def analyst_node(state: DebateState):
    prompt = f"Analyse news et sentiment pour ce marché Polymarket: {state['market']['question']}"
    resp = completion(model=settings.default_llm_analyst, messages=[{"role": "system", "content": prompt}], temperature=0.3)
    state["news_context"] = resp.choices[0].message.content
    return state

def onchain_node(state: DebateState):
    # Placeholder Dune MCP
    state["onchain_context"] = "Onchain neutral context (Dune MCP)"
    return state

def judge_node(state: DebateState):
    prompt = f"""Synthèse finale pour le marché: {state['market']['question']}
News: {state.get('news_context', '')}
Onchain: {state.get('onchain_context', '')}
Prix actuel: {state['market'].get('price', 0.5)}

Retourne uniquement un JSON valide avec les champs de AgentOutput."""
    resp = completion(model=settings.default_llm_judge, messages=[{"role": "system", "content": prompt}], temperature=0.0, response_format={"type": "json_object"})
    try:
        data = json.loads(resp.choices[0].message.content)
        state["result"] = AgentOutput(**data)
    except:
        state["result"] = AgentOutput(prob_true_yes=0.5, confidence=50, edge=0.0, rationale="Parse error", side="YES")
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