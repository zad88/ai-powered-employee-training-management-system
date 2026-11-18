from typing import Any, TypedDict


class TNAAgentState(TypedDict):
    """Shared state passed between TNA Agent workflow nodes."""

    company_id: int

    # Existing deterministic TNA analysis
    tna_analysis: dict[str, Any]

    # Privacy-safe, aggregated context for the LLM
    safe_context: dict[str, Any]

    # AI-generated insights
    ai_insights: dict[str, Any]

    # Workflow status and errors
    status: str
    error: str | None
