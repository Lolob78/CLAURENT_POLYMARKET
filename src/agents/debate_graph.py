"""Débat multi-LLM avec ASYNC pour parallélisation."""
from langgraph.graph import StateGraph, END
from src.config import settings
from src.agents.structured_output import AgentOutput
from src.ingestion.dune_mcp import query_dune_mcp
import aiohttp
import asyncio
import os
import json
import re

class DebateState(dict):
    market: dict
    news_context: str = ""
    onchain_context: str = ""
    result: AgentOutput | None = None


async def call_grok_async(prompt: str, retries: int = 3) -> str:
    """Appel ASYNC à l'API xAI Grok avec retry exponentiel."""
    grok_key = os.getenv("GROK_API_KEY")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {grok_key}"
    }
    data = {
        "model": "grok-4-1-fast-non-reasoning",
        "input": prompt
    }
    for attempt in range(retries):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.x.ai/v1/responses",
                    headers=headers,
                    json=data,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    result = await response.json()
                    return result['output'][0]['content'][0]['text']
        except Exception as e:
            if attempt < retries - 1:
                await asyncio.sleep(2 ** attempt)
            else:
                print(f"❌ Grok échoué après {retries} tentatives: {e}")
    return ""


def extract_json(text: str) -> dict | None:
    """Extrait le premier bloc JSON valide d'une réponse texte."""
    # Cherche un bloc ```json ... ``` en priorité
    match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if not match:
        # Sinon, prend le premier { ... } de la réponse
        match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1) if match.lastindex else match.group())
        except json.JSONDecodeError:
            return None
    return None


async def analyst_node(state: DebateState):
    """Analyse news/sentiment avec Grok."""
    question = state['market']['question']
    prompt = f"Analyse brièvement le sentiment pour ce marché de prédiction: {question}\nRéponds en 2-3 phrases factuelles."
    state["news_context"] = await call_grok_async(prompt)
    return state


async def onchain_node(state: DebateState):
    """Contexte onchain via Dune MCP."""
    condition_id = state['market'].get('condition_id', '')
    state["onchain_context"] = await asyncio.to_thread(query_dune_mcp, condition_id)
    return state


async def judge_node(state: DebateState):
    """Jugement final avec Grok — synthèse news + onchain + prix."""
    price = state['market'].get('price', 0.5)
    prompt = f"""Tu es un juge rationnel pour les marchés de prédiction.

Marché: {state['market']['question']}
Prix actuel: {price:.2f} (probabilité implicite du marché)
Analyse news/sentiment: {state.get('news_context', 'N/A')}
Contexte onchain: {state.get('onchain_context', 'N/A')}

Calcule ton estimation de la probabilité réelle que l'événement se produise (YES).
L'edge = abs(ta_probabilité - prix_marché).

Retourne UNIQUEMENT un JSON valide, sans texte autour:
{{
  "prob_true_yes": 0.XX,
  "confidence": XX,
  "edge": 0.XX,
  "rationale": "explication courte",
  "side": "YES"
}}

Règle: side=YES si prob_true_yes > prix, side=NO sinon. edge = abs(prob_true_yes - {price:.2f})."""

    try:
        response_text = await asyncio.wait_for(call_grok_async(prompt), timeout=8.0)
        data = extract_json(response_text)

        if data:
            try:
                state["result"] = AgentOutput(**data)
            except Exception:
                state["result"] = AgentOutput(
                    prob_true_yes=0.5, confidence=50, edge=0.0,
                    rationale=f"Validation error: {data}", side="YES"
                )
        else:
            state["result"] = AgentOutput(
                prob_true_yes=0.5, confidence=50, edge=0.0,
                rationale="JSON parse error", side="YES"
            )
    except asyncio.TimeoutError:
        logger.warning("grok_timeout", market=state['market'].get('question', '')[:30])
        state["result"] = AgentOutput(
            prob_true_yes=0.5, confidence=50, edge=0.0,
            rationale="Grok API timeout", side="YES"
        )
    except Exception as e:
        logger.error("grok_error", error=str(e))
        state["result"] = AgentOutput(
            prob_true_yes=0.5, confidence=50, edge=0.0,
            rationale=f"Grok error: {str(e)}", side="YES"
        )
    return statedef judge_node(state: DebateState):
    """Jugement final avec Grok — synthèse news + onchain + prix."""
    price = state['market'].get('price', 0.5)
    prompt = f"""Tu es un juge rationnel pour les marchés de prédiction.

Marché: {state['market']['question']}
Prix actuel: {price:.2f} (probabilité implicite du marché)
Analyse news/sentiment: {state.get('news_context', 'N/A')}
Contexte onchain: {state.get('onchain_context', 'N/A')}

Calcule ton estimation de la probabilité réelle que l'événement se produise (YES).
L'edge = abs(ta_probabilité - prix_marché).

Retourne UNIQUEMENT un JSON valide, sans texte autour:
{{
  "prob_true_yes": 0.XX,
  "confidence": XX,
  "edge": 0.XX,
  "rationale": "explication courte",
  "side": "YES"
}}

Règle: side=YES si prob_true_yes > prix, side=NO sinon. edge = abs(prob_true_yes - {price:.2f})."""

    try:
        response_text = await asyncio.wait_for(call_grok_async(prompt), timeout=8.0)
    except asyncio.TimeoutError:
        logger.warning("grok_timeout", market=state["market"].get("question", "")[:30])
        state["result"] = AgentOutput(
            prob_true_yes=0.5, confidence=50, edge=0.0,
            rationale="Grok API timeout", side="YES"
        )
        return state
    except Exception as e:
        logger.error("grok_error", error=str(e))
        state["result"] = AgentOutput(
            prob_true_yes=0.5, confidence=50, edge=0.0,
            rationale=f"Grok error: {str(e)}", side="YES"
        )
        return state
    data = extract_json(response_text)

    if data:
        try:
            state["result"] = AgentOutput(**data)
        except Exception:
            state["result"] = AgentOutput(
                prob_true_yes=0.5, confidence=50, edge=0.0,
                rationale=f"Validation error: {data}", side="YES"
            )
    else:
        state["result"] = AgentOutput(
            prob_true_yes=0.5, confidence=50, edge=0.0,
            rationale="JSON parse error", side="YES"
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
