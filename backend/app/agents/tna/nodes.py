import json
from typing import Any

from backend.app.agents.tna.context import prepare_safe_tna_context
from backend.app.agents.tna.state import TNAAgentState
from backend.app.core.llm import get_llm


def prepare_tna_context(state: TNAAgentState) -> dict[str, Any]:
    safe_context = prepare_safe_tna_context(state["tna_analysis"])

    return {
        "safe_context": safe_context,
        "status": "context_prepared",
        "error": None,
    }


def validate_tna_insights(insights: Any) -> None:
    """Validate the structure and contents of AI-generated insights."""

    if not isinstance(insights, dict):
        raise ValueError("AI response must be a JSON object.")

    expected_fields = {
        "overall_summary",
        "key_findings",
        "data_limitations",
        "recommended_actions",
        "suggested_skills_for_review",
    }

    if set(insights) != expected_fields:
        raise ValueError("AI response contains missing or unexpected fields.")

    def check_text(value: Any, field: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} must be a non-empty string.")

    check_text(insights["overall_summary"], "overall_summary")

    list_fields = [
        "key_findings",
        "data_limitations",
        "recommended_actions",
        "suggested_skills_for_review",
    ]

    for field in list_fields:
        if not isinstance(insights[field], list):
            raise ValueError(f"{field} must be a list.")

    for i, finding in enumerate(insights["key_findings"]):
        if not isinstance(finding, dict) or set(finding) != {
            "finding", "evidence"
        }:
            raise ValueError(f"key_findings[{i}] has an invalid structure.")

        check_text(finding["finding"], f"key_findings[{i}].finding")
        check_text(finding["evidence"], f"key_findings[{i}].evidence")

    for i, limitation in enumerate(insights["data_limitations"]):
        check_text(limitation, f"data_limitations[{i}]")

    for i, action in enumerate(insights["recommended_actions"]):
        if not isinstance(action, dict) or set(action) != {
            "action", "reason", "priority"
        }:
            raise ValueError(
                f"recommended_actions[{i}] has an invalid structure."
            )

        check_text(action["action"], f"recommended_actions[{i}].action")
        check_text(action["reason"], f"recommended_actions[{i}].reason")

        if action["priority"] not in {"High", "Medium", "Low"}:
            raise ValueError(f"recommended_actions[{i}] has invalid priority.")

    for i, suggestion in enumerate(insights["suggested_skills_for_review"]):
        if not isinstance(suggestion, dict) or set(suggestion) != {
            "job_title", "skill_name", "reason", "status"
        }:
            raise ValueError(
                f"suggested_skills_for_review[{i}] has an invalid structure."
            )

        check_text(suggestion["job_title"], f"suggestions[{i}].job_title")
        check_text(suggestion["skill_name"], f"suggestions[{i}].skill_name")
        check_text(suggestion["reason"], f"suggestions[{i}].reason")

        if suggestion["status"] != "Requires Training Manager approval":
            raise ValueError(
                f"suggested_skills_for_review[{i}] has an invalid status."
            )


def generate_tna_insights(state: TNAAgentState) -> dict[str, Any]:
    """Generate and validate AI insights."""

    safe_context = state.get("safe_context")

    if not safe_context:
        return {
            "status": "failed",
            "error": "Privacy-safe TNA context is missing.",
        }

    prompt = f"""
You are an AI Training Need Analysis assistant.

Analyze the following aggregated company training data.

DATA:
{json.dumps(safe_context, ensure_ascii=False, indent=2)}

RULES:
1. Use only supplied data as evidence.
2. Never invent employee skill levels, gaps, or company facts.
3. Only approved job skill requirements are official.
4. Pending requirements are not approved.
5. Missing assessments do not mean zero proficiency.
6. Suggested skills require Training Manager approval.
7. Explain when information is insufficient.
8. Never identify individual employees.

Return JSON only, using exactly this structure:
{{
  "overall_summary": "Summary",
  "key_findings": [
    {{"finding": "Description", "evidence": "Supporting evidence"}}
  ],
  "data_limitations": ["Limitation"],
  "recommended_actions": [
    {{"action": "Action", "reason": "Reason", "priority": "High"}}
  ],
  "suggested_skills_for_review": [
    {{
      "job_title": "Position",
      "skill_name": "Skill",
      "reason": "Reason",
      "status": "Requires Training Manager approval"
    }}
  ]
}}
"""

    try:
        response = get_llm().invoke(prompt)

        if not isinstance(response.content, str) or not response.content.strip():
            raise ValueError("OpenAI returned an empty or unsupported response.")

        raw_response = response.content.strip()

        if raw_response.startswith("```"):
            raw_response = raw_response.split("\n", 1)[1]
            raw_response = raw_response.rsplit("```", 1)[0].strip()

        insights = json.loads(raw_response)
        validate_tna_insights(insights)

        return {
            "ai_insights": insights,
            "status": "insights_generated",
            "error": None,
        }

    except Exception as error:
        return {
            "status": "failed",
            "error": f"{type(error).__name__}: {error}",
        }
