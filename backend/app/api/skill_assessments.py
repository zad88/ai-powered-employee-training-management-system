from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.api.dependencies import (
    AuthContext,
    allowed_employee_ids,
    ensure_employee_access,
    get_auth_context,
    get_db,
    get_membership_employee,
)

from backend.app.db.skill_assessment import SkillAssessment
from backend.app.db.employee import Employee
from backend.app.db.skill import Skill

from backend.app.schemas.skill_assessment import (
    SkillAssessmentCreate,
    SkillAssessmentUpdate,
    SkillAssessmentReview,
    SkillAssessmentResponse,
)


router = APIRouter(
    prefix="/skill-assessments",
    tags=["Skill Assessments"]
)


@router.post(
    "/",
    response_model=SkillAssessmentResponse,
    status_code=201
)
def create_skill_assessment(
    company_id: int,
    assessment_data: SkillAssessmentCreate,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    if company_id <= 0:
        raise HTTPException(
            status_code=422,
            detail="Invalid company ID"
        )

    employee = ensure_employee_access(
        context,
        db,
        assessment_data.employee_id,
    )
    if (
        context.role == "Employee"
        and assessment_data.assessment_source != "Self-Assessment"
    ):
        raise HTTPException(
            status_code=422,
            detail="Employees may only submit self-assessments.",
        )
    actor = get_membership_employee(context, db, required=False)

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
        assessed_by=actor.id if actor else None,
        assessed_by_user_id=context.user.user_id,
        evidence_status="Pending Review"
    )

    try:
        db.add(new_assessment)
        db.commit()
        db.refresh(new_assessment)
    except Exception:
        db.rollback()
        raise

    return new_assessment


@router.get(
    "/",
    response_model=list[SkillAssessmentResponse]
)
def get_skill_assessments(
    company_id: int,
    employee_id: int | None = None,
    skill_id: int | None = None,
    evidence_status: str | None = None,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    query = db.query(SkillAssessment).filter(
        SkillAssessment.company_id == company_id
    )
    employee_ids = allowed_employee_ids(context, db)
    if employee_ids is not None:
        query = query.filter(SkillAssessment.employee_id.in_(employee_ids))

    if employee_id is not None:
        query = query.filter(
            SkillAssessment.employee_id == employee_id
        )

    if skill_id is not None:
        query = query.filter(
            SkillAssessment.skill_id == skill_id
        )

    if evidence_status is not None:
        if evidence_status not in (
            "Pending Review",
            "Approved",
            "Rejected"
        ):
            raise HTTPException(
                status_code=422,
                detail="Invalid evidence status"
            )

        query = query.filter(
            SkillAssessment.evidence_status == evidence_status
        )

    return query.order_by(
        SkillAssessment.assessment_date.desc(),
        SkillAssessment.assessment_id.desc()
    ).all()


@router.get(
    "/{assessment_id}",
    response_model=SkillAssessmentResponse
)
def get_skill_assessment(
    assessment_id: int,
    company_id: int,
    context: AuthContext = Depends(get_auth_context),
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

    ensure_employee_access(context, db, assessment.employee_id)
    return assessment


@router.put(
    "/{assessment_id}",
    response_model=SkillAssessmentResponse
)
def update_skill_assessment(
    assessment_id: int,
    company_id: int,
    assessment_data: SkillAssessmentUpdate,
    context: AuthContext = Depends(get_auth_context),
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

    ensure_employee_access(context, db, assessment.employee_id)
    update_data = assessment_data.model_dump(
        exclude_unset=True
    )

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

    evidence_fields = {
        "proficiency_level",
        "assessment_source",
        "assessment_score",
        "evidence_quality",
        "evidence_title",
        "evidence_description",
        "assessment_date",
        "expiry_date",
        "assessor_comments",
    }

    evidence_changed = any(
        field in evidence_fields
        for field in update_data
    )

    for field, value in update_data.items():
        setattr(assessment, field, value)

    if evidence_changed:
        assessment.evidence_status = "Pending Review"
        assessment.reviewed_by = None
        assessment.reviewed_by_user_id = None

    try:
        db.commit()
        db.refresh(assessment)
    except Exception:
        db.rollback()
        raise

    return assessment


@router.put(
    "/{assessment_id}/review",
    response_model=SkillAssessmentResponse
)
def review_skill_assessment(
    assessment_id: int,
    company_id: int,
    review_data: SkillAssessmentReview,
    context: AuthContext = Depends(get_auth_context),
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

    ensure_employee_access(context, db, assessment.employee_id)
    assessment.evidence_status = review_data.evidence_status
    reviewer = get_membership_employee(context, db, required=False)
    assessment.reviewed_by = reviewer.id if reviewer else None
    assessment.reviewed_by_user_id = context.user.user_id

    try:
        db.commit()
        db.refresh(assessment)
    except Exception:
        db.rollback()
        raise

    return assessment


@router.delete("/{assessment_id}")
def delete_skill_assessment(
    assessment_id: int,
    company_id: int,
    context: AuthContext = Depends(get_auth_context),
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

    ensure_employee_access(context, db, assessment.employee_id)
    try:
        db.delete(assessment)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "message": "Skill assessment deleted successfully"
    }
