from langgraph.graph import END, START, StateGraph

from backend.app.agents.tna.state import TNAAgentState
from backend.app.agents.tna.nodes import (
    prepare_tna_context,
    generate_tna_insights,
)


def build_tna_graph():
    """Build and compile the TNA Agent workflow."""

    workflow = StateGraph(TNAAgentState)

    workflow.add_node("prepare_context", prepare_tna_context)
    workflow.add_node("generate_insights", generate_tna_insights)

    workflow.add_edge(START, "prepare_context")
    workflow.add_edge("prepare_context", "generate_insights")
    workflow.add_edge("generate_insights", END)

    return workflow.compile()


tna_graph = build_tna_graph()
