from typing import Any


def prepare_safe_tna_context(tna_analysis: dict[str, Any]) -> dict[str, Any]:
    """
    Prepare aggregated, privacy-safe TNA information for AI analysis.

    Employee names, IDs, codes, and individual assessment records
    are deliberately excluded.
    """

    summary = tna_analysis.get("summary", {})

    safe_positions = []

    for position in tna_analysis.get("position_analysis", []):
        safe_positions.append({
            "job_title": position.get("job_title"),
            "employee_count": position.get("employee_count", 0),
            "approved_requirements": [
                {
                    "skill_name": item.get("skill_name"),
                    "category": item.get("category"),
                    "required_proficiency": item.get(
                        "required_proficiency"
                    ),
                    "importance": item.get("importance"),
                }
                for item in position.get("approved_requirements", [])
            ],
            "pending_requirement_count": position.get(
                "pending_requirement_count", 0
            ),
            "rejected_requirement_count": position.get(
                "rejected_requirement_count", 0
            ),
        })

    safe_departments = []

    for department in tna_analysis.get("department_analysis", []):
        safe_departments.append({
            "employee_count": department.get("employee_count", 0),
            "confirmed_skill_gaps": department.get(
                "confirmed_skill_gaps", 0
            ),
            "assessments_needed": department.get(
                "assessments_needed", 0
            ),
            "common_skill_gaps": department.get(
                "common_skill_gaps", []
            ),
        })

    return {
        "analysis_date": str(tna_analysis.get("analysis_date")),
        "summary": {
            "active_employees": summary.get("active_employees", 0),
            "positions_analysed": summary.get("positions_analysed", 0),
            "confirmed_skill_gaps": summary.get(
                "confirmed_skill_gaps", 0
            ),
            "assessments_needed": summary.get("assessments_needed", 0),
        },
        "positions": safe_positions,
        "departments": safe_departments,
        "data_limitations": [
            (
                "Only approved job skill requirements are treated "
                "as official requirements."
            ),
            (
                "Pending and rejected requirements are not used "
                "to calculate confirmed skill gaps."
            ),
            (
                "Missing assessments must not be interpreted "
                "as zero proficiency."
            ),
            (
                "Unconfigured skills cannot be confirmed by "
                "the current rule-based analysis."
            ),
            (
                "AI-proposed skills are suggestions only and "
                "require Training Manager review."
            ),
        ],
    }
