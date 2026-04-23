"""Débat multi-LLM avec mocking pour tests sans coûts."""
from langgraph.graph import StateGraph, END
# from litellm import completion  # ← MOCK: commenté
from src.config import settings
from src.agents.structured_output import AgentOutput
import random
import json

class DebateState(dict):
    market: dict
    news_context: str = ""
    onchain_context: str = ""
    result: AgentOutput | None = None


def analyst_node(state: DebateState):
    """Mock: génère du sentiment d'analyse sans appel LLM."""
    # Version réelle (commentée):
    # prompt = f"Analyse news et sentiment pour ce marché Polymarket: {state['market']['question']}"
    # resp = completion(model=settings.default_llm_analyst, messages=[{"role": "system", "content": prompt}], temperature=0.3)
    # state["news_context"] = resp.choices[0].message.content
    
    # Version mock:
    question = state['market']['question']
    sentiments = [
        f"Sentiment positif détecté pour '{question[:40]}...'. Discussions actives, momentum haussier.",
        f"Sentiment mitigé pour '{question[:40]}...'. Pas de consensus clair, volatilité attendue.",
        f"Sentiment négatif pour '{question[:40]}...'. Préoccupations exprimées, pression baissière.",
    ]
    state["news_context"] = random.choice(sentiments)
    return state


def onchain_node(state: DebateState):
    """Contexte onchain simulé."""
    state["onchain_context"] = "Onchain activity neutral - whale monitoring in progress"
    return state


def judge_node(state: DebateState):
    """Mock: génère un résultat d'analyse réaliste sans appel LLM."""
    # Version réelle (commentée):
    # prompt = f"""Synthèse finale pour le marché: {state['market']['question']}
    # News: {state.get('news_context', '')}
    # Onchain: {state.get('onchain_context', '')}
    # Prix actuel: {state['market'].get('price', 0.5)}
    # Retourne uniquement un JSON valide avec les champs de AgentOutput."""
    # resp = completion(model=settings.default_llm_judge, messages=[{"role": "system", "content": prompt}], temperature=0.0, response_format={"type": "json_object"})
    # try:
    #     data = json.loads(resp.choices[0].message.content)
    #     state["result"] = AgentOutput(**data)
    # except:
    #     state["result"] = AgentOutput(prob_true_yes=0.5, confidence=50, edge=0.0, rationale="Parse error", side="YES")
    
    # Version mock:
    edge = round(random.uniform(0.05, 0.35), 2)
    
    if edge < settings.edge_min:
        prob = round(random.uniform(0.35, 0.65), 2)
    else:
        prob = round(random.uniform(0.45, 0.75), 2)
    
    confidence = max(30, min(95, int(edge * 200 + random.randint(-10, 10))))
    side = random.choice(["YES", "NO"])
    
    rationales = [
        f"Prix actuel {state['market'].get('price', 0.5):.2f} avec momentum {side.lower()}. Edge détecté via sentiment analysis.",
        f"Conflit détecté dans les sources. Probabilité {prob*100:.0f}% basée sur onchain metrics.",
        f"Débat {side} - risque/reward ratio favorable. Conviction: {confidence}%",
        f"Analyse technique + sentiment = {side}. Edge calculé à {edge*100:.0f}%",
    ]
    
    state["result"] = AgentOutput(
        prob_true_yes=prob,
        confidence=confidence,
        edge=edge,
        rationale=random.choice(rationales),
        side=side
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