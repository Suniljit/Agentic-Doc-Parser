"""Part 3 — LangGraph multi-agent supervisor over FY2024 budget RAG store."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Literal, TypedDict

import yaml
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from loguru import logger

from utils.logging_config import setup_file_logging
from utils.parser import parse_pdf
from utils.rag import build_store, get_retriever_tool

logger.remove()
logger.add(sys.stderr, level=os.getenv("LOG_LEVEL", "INFO"))

PDF_PATH = Path("data/fy2024_analysis_of_revenue_and_expenditure.pdf")
CACHE_DIR = Path("data/cache")
CHROMA_DIR = Path("data/chroma")

_PROMPTS = yaml.safe_load((Path(__file__).parent / "prompts.yaml").read_text())

DEMO_QUERIES = [
    (
        "What are the key government revenue streams, and how will the Budget"
        " for the Future Energy Fund be supported?"
    ),
    "What is the corporate income tax rate and how does it compare to previous years?",
    "How much has been allocated to the Future Energy Fund and what does it cover?",
]


class AgentState(TypedDict):
    query: str
    revenue_query: str
    expenditure_query: str
    revenue_output: str
    expenditure_output: str
    final_answer: str
    next: Literal["revenue", "expenditure", "both", "reject"]


# Used only for logging purposes to keep track of retrieved chunks; not part of the agent state
def _split_chunks(context: str) -> list[str]:
    return re.split(r"\n\n(?=\[)", context)


def build_graph(search_document):
    """Build and compile the LangGraph supervisor graph."""
    supervisor_llm = ChatOpenAI(model="gpt-4o", max_completion_tokens=256, temperature=0)
    agent_llm = ChatOpenAI(model="gpt-4o", max_completion_tokens=512, temperature=0)
    synthesizer_llm = ChatOpenAI(model="gpt-4o", max_completion_tokens=1024, temperature=0)

    def supervisor_node(state: AgentState) -> dict:
        response = supervisor_llm.invoke(
            [
                SystemMessage(content=_PROMPTS["part3"]["supervisor"]),
                HumanMessage(content=state["query"]),
            ]
        )
        try:
            result = json.loads(response.content)
            decision = result.get("next", "reject")
            revenue_query = result.get("revenue_query", "")
            expenditure_query = result.get("expenditure_query", "")
        except json.JSONDecodeError:
            logger.warning("Supervisor returned malformed JSON; rejecting")
            decision = "reject"
            revenue_query = ""
            expenditure_query = ""

        # Downgrade "both" if one sub-query is missing
        if decision == "both":
            if not revenue_query and not expenditure_query:
                decision = "reject"
            elif not revenue_query:
                decision = "expenditure"
            elif not expenditure_query:
                decision = "revenue"

        logger.info("Supervisor routed to: {}", decision)
        return {
            "next": decision,
            "revenue_query": revenue_query,
            "expenditure_query": expenditure_query,
        }

    def route_supervisor(state: AgentState):
        decision = state["next"]
        if decision == "both":
            return ["revenue_agent", "expenditure_agent"]
        mapping = {
            "revenue": "revenue_agent",
            "expenditure": "expenditure_agent",
            "reject": "reject_node",
        }
        if decision not in mapping:
            logger.warning("Unexpected supervisor decision '{}'; rejecting", decision)
            return "reject_node"
        return mapping[decision]

    def revenue_node(state: AgentState) -> dict:
        sub_query = state["revenue_query"]
        logger.info("Revenue agent sub-query: {}", sub_query)
        context = search_document.invoke(sub_query)
        chunks = _split_chunks(context)
        logger.debug("Revenue agent retrieved {} chunk(s)", len(chunks))
        for i, chunk in enumerate(chunks, 1):
            logger.debug("Revenue chunk {}/{}:\n{}", i, len(chunks), chunk)
        response = agent_llm.invoke(
            [
                SystemMessage(content=_PROMPTS["part3"]["revenue_agent"]),
                HumanMessage(
                    content=(
                        f"Context:\n{context}\n\n"
                        f"Original question: {state['query']}\n"
                        f"Your focus: {sub_query}\n\n"
                        "Answer the focused question using the context. "
                        "Another agent is handling the other parts of the original question."
                    )
                ),
            ]
        )
        answer = response.content
        logger.info("Revenue agent answer: {}", answer)
        return {"revenue_output": answer}

    def expenditure_node(state: AgentState) -> dict:
        sub_query = state["expenditure_query"]
        logger.info("Expenditure agent sub-query: {}", sub_query)
        context = search_document.invoke(sub_query)
        chunks = _split_chunks(context)
        logger.debug("Expenditure agent retrieved {} chunk(s)", len(chunks))
        for i, chunk in enumerate(chunks, 1):
            logger.debug("Expenditure chunk {}/{}:\n{}", i, len(chunks), chunk)
        response = agent_llm.invoke(
            [
                SystemMessage(content=_PROMPTS["part3"]["expenditure_agent"]),
                HumanMessage(
                    content=(
                        f"Context:\n{context}\n\n"
                        f"Original question: {state['query']}\n"
                        f"Your focus: {sub_query}\n\n"
                        "Answer the focused question using the context. "
                        "Another agent is handling the other parts of the original question."
                    )
                ),
            ]
        )
        answer = response.content
        logger.info("Expenditure agent answer: {}", answer)
        return {"expenditure_output": answer}

    def reject_node(state: AgentState) -> dict:
        logger.warning("Query rejected as off-topic: {}", state["query"])
        return {
            "final_answer": (
                "This system only answers questions about the Singapore FY2024 budget document "
                "(revenue, expenditure, and fiscal policy). Please ask a related question."
            )
        }

    def synthesizer_node(state: AgentState) -> dict:
        parts = []
        if state["revenue_output"]:
            parts.append(f"Revenue Agent:\n{state['revenue_output']}")
        if state["expenditure_output"]:
            parts.append(f"Expenditure Agent:\n{state['expenditure_output']}")
        combined = "\n\n".join(parts)
        response = synthesizer_llm.invoke(
            [
                SystemMessage(content=_PROMPTS["part3"]["synthesizer"]),
                HumanMessage(
                    content=f"Agent outputs:\n{combined}\n\nOriginal question: {state['query']}"
                ),
            ]
        )
        answer = response.content
        logger.info("Final answer: {}", answer)
        return {"final_answer": answer}

    graph = StateGraph(AgentState)
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("revenue_agent", revenue_node)
    graph.add_node("expenditure_agent", expenditure_node)
    graph.add_node("reject_node", reject_node)
    graph.add_node("synthesizer", synthesizer_node)

    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges("supervisor", route_supervisor)
    graph.add_edge("revenue_agent", "synthesizer")
    graph.add_edge("expenditure_agent", "synthesizer")
    graph.add_edge("synthesizer", END)
    graph.add_edge("reject_node", END)

    return graph.compile()


def run_query(compiled_graph, query: str) -> str:
    logger.info("Running query: {}", query)
    result = compiled_graph.invoke(
        {
            "query": query,
            "revenue_query": "",
            "expenditure_query": "",
            "revenue_output": "",
            "expenditure_output": "",
            "final_answer": "",
            "next": "revenue",
        }
    )
    return result["final_answer"]


def main() -> None:
    setup_file_logging("part3")
    markdown = parse_pdf(PDF_PATH, CACHE_DIR)
    vectorstore = build_store(markdown, CHROMA_DIR)
    search_document = get_retriever_tool(vectorstore)
    graph = build_graph(search_document)

    if len(sys.argv) > 1:
        query = sys.argv[1]
        run_query(graph, query)
    else:
        for i, query in enumerate(DEMO_QUERIES, 1):
            logger.info("--- Demo query {} of {} ---", i, len(DEMO_QUERIES))
            run_query(graph, query)


if __name__ == "__main__":
    main()
