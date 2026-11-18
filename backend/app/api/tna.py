from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_db
from backend.app.services.tna_service import analyze_company_tna
from backend.app.agents.tna.graph import tna_graph


router = APIRouter(
    prefix="/tna",
    tags=["Training Need Analysis"]
)


@router.get("/")
def get_company_tna(
    company_id: int,
    db: Session = Depends(get_db)
):
    """Return the existing rule-based TNA analysis."""

    if company_id <= 0:
        raise HTTPException(
            status_code=400,
            detail="Company ID must be a positive integer"
        )

    return analyze_company_tna(
        db=db,
        company_id=company_id
    )


@router.post("/ai-analysis")
def run_ai_tna_analysis(
    company_id: int,
    db: Session = Depends(get_db)
):
    """Run rule-based TNA analysis followed by the LangGraph AI workflow."""

    if company_id <= 0:
        raise HTTPException(
            status_code=400,
            detail="Company ID must be a positive integer"
        )

    # Step 1: Run the existing deterministic analysis.
    analysis = analyze_company_tna(
        db=db,
        company_id=company_id
    )

    # Step 2: Prepare the initial LangGraph state.
    initial_state = {
        "company_id": company_id,
        "tna_analysis": analysis,
        "safe_context": {},
        "ai_insights": {},
        "status": "started",
        "error": None,
    }

    # Step 3: Execute the AI workflow.
    result = tna_graph.invoke(initial_state)

    return {
        "company_id": company_id,
        "status": result.get("status"),
        "rule_based_analysis": analysis,
        "safe_context": result.get("safe_context"),
        "ai_insights": result.get("ai_insights"),
        "error": result.get("error"),
    }
