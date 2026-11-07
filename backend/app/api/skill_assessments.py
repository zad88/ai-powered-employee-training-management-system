from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_db

from backend.app.db.skill_assessment import SkillAssessment
from backend.app.db.employee import Employee
from backend.app.db.skill import Skill

from backend.app.schemas.skill_assessment import (
    SkillAssessmentCreate,
    SkillAssessmentUpdate,
    SkillAssessmentReview,
    SkillAssessmentResponse
)


router = APIRouter(
    prefix="/skill-assessments",
    tags=["Skill Assessments"]
)


# 1. CREATE SKILL ASSESSMENT
@router.post("/", response_model=SkillAssessmentResponse, status_code=201)
def create_skill_assessment(
    company_id: int,
    assessment_data: SkillAssessmentCreate,
    db: Session = Depends(get_db)
):
    employee = db.query(Employee).filter(
        Employee.id == assessment_data.employee_id,
        Employee.company_id == company_id,
        Employee.is_active == True
    ).first()

    if employee is None:
        raise HTTPException(
            status_code=404,
            detail="Employee not found in this company"
        )

    skill = db.query(Skill).filter(
        Skill.skill_id == assessment_data.skill_id
    ).first()

    if skill is None:
        raise HTTPException(
            status_code=404,
            detail="Skill not found"
        )

    new_assessment = SkillAssessment(
        **assessment_data.model_dump(),
        company_id=company_id,
        evidence_status="Pending Review"
    )

    db.add(new_assessment)
    db.commit()
    db.refresh(new_assessment)

    return new_assessment


# 2. GET ALL SKILL ASSESSMENTS
@router.get("/", response_model=list[SkillAssessmentResponse])
def get_skill_assessments(
    company_id: int,
    employee_id: int | None = None,
    skill_id: int | None = None,
    evidence_status: str | None = None,
    db: Session = Depends(get_db)
):
    query = db.query(SkillAssessment).filter(
        SkillAssessment.company_id == company_id
    )

    if employee_id is not None:
        query = query.filter(
            SkillAssessment.employee_id == employee_id
        )

    if skill_id is not None:
        query = query.filter(
            SkillAssessment.skill_id == skill_id
        )

    if evidence_status is not None:
        query = query.filter(
            SkillAssessment.evidence_status == evidence_status
        )

    return query.order_by(
        SkillAssessment.assessment_date.desc()
    ).all()


# 3. GET ONE SKILL ASSESSMENT
@router.get("/{assessment_id}", response_model=SkillAssessmentResponse)
def get_skill_assessment(
    assessment_id: int,
    company_id: int,
    db: Session = Depends(get_db)
):
    assessment = db.query(SkillAssessment).filter(
        SkillAssessment.assessment_id == assessment_id,
        SkillAssessment.company_id == company_id
    ).first()

    if assessment is None:
        raise HTTPException(
            status_code=404,
            detail="Skill assessment not found"
        )

    return assessment


# 4. UPDATE SKILL ASSESSMENT
@router.put("/{assessment_id}", response_model=SkillAssessmentResponse)
def update_skill_assessment(
    assessment_id: int,
    company_id: int,
    assessment_data: SkillAssessmentUpdate,
    db: Session = Depends(get_db)
):
    assessment = db.query(SkillAssessment).filter(
        SkillAssessment.assessment_id == assessment_id,
        SkillAssessment.company_id == company_id
    ).first()

    if assessment is None:
        raise HTTPException(
            status_code=404,
            detail="Skill assessment not found"
        )

    update_data = assessment_data.model_dump(exclude_unset=True)

    new_assessment_date = update_data.get(
        "assessment_date",
        assessment.assessment_date
    )

    new_expiry_date = update_data.get(
        "expiry_date",
        assessment.expiry_date
    )

    if (
        new_expiry_date is not None
        and new_expiry_date < new_assessment_date
    ):
        raise HTTPException(
            status_code=422,
            detail="Expiry date cannot be before assessment date"
        )

    for field, value in update_data.items():
        setattr(assessment, field, value)

    # Updated evidence must be reviewed again.
    if update_data:
        assessment.evidence_status = "Pending Review"

    db.commit()
    db.refresh(assessment)

    return assessment


# 5. APPROVE OR REJECT EVIDENCE
@router.put("/{assessment_id}/review", response_model=SkillAssessmentResponse)
def review_skill_assessment(
    assessment_id: int,
    company_id: int,
    review_data: SkillAssessmentReview,
    db: Session = Depends(get_db)
):
    assessment = db.query(SkillAssessment).filter(
        SkillAssessment.assessment_id == assessment_id,
        SkillAssessment.company_id == company_id
    ).first()

    if assessment is None:
        raise HTTPException(
            status_code=404,
            detail="Skill assessment not found"
        )

    assessment.evidence_status = review_data.evidence_status

    db.commit()
    db.refresh(assessment)

    return assessment


# 6. DELETE SKILL ASSESSMENT
@router.delete("/{assessment_id}")
def delete_skill_assessment(
    assessment_id: int,
    company_id: int,
    db: Session = Depends(get_db)
):
    assessment = db.query(SkillAssessment).filter(
        SkillAssessment.assessment_id == assessment_id,
        SkillAssessment.company_id == company_id
    ).first()

    if assessment is None:
        raise HTTPException(
            status_code=404,
            detail="Skill assessment not found"
        )

    db.delete(assessment)
    db.commit()

    return {
        "message": "Skill assessment deleted successfully"
    }