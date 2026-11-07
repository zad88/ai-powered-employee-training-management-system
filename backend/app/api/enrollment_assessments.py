from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_db

from backend.app.db.enrollment import Enrollment
from backend.app.db.enrollment_assessment import EnrollmentAssessment

from backend.app.schemas.enrollment_assessment import (
    EnrollmentAssessmentCreate,
    EnrollmentAssessmentUpdate,
    EnrollmentAssessmentResponse,
)


router = APIRouter(
    prefix="/enrollment-assessments",
    tags=["Enrollment Assessments"]
)


# 1. CREATE ASSESSMENT ATTEMPT
@router.post(
    "/",
    response_model=EnrollmentAssessmentResponse,
    status_code=201
)
def create_enrollment_assessment(
    company_id: int,
    assessment_data: EnrollmentAssessmentCreate,
    db: Session = Depends(get_db)
):
    enrollment = db.query(Enrollment).filter(
        Enrollment.enrollment_id == assessment_data.enrollment_id,
        Enrollment.company_id == company_id
    ).first()

    if enrollment is None:
        raise HTTPException(
            status_code=404,
            detail="Enrollment not found"
        )

    if enrollment.status not in ["In Progress", "Completed"]:
        raise HTTPException(
            status_code=400,
            detail="Assessment requires an active or completed enrollment"
        )

    existing_attempt = db.query(EnrollmentAssessment).filter(
        EnrollmentAssessment.enrollment_id == assessment_data.enrollment_id,
        EnrollmentAssessment.attempt_number == assessment_data.attempt_number
    ).first()

    if existing_attempt:
        raise HTTPException(
            status_code=409,
            detail="This assessment attempt number already exists"
        )

    assessment = EnrollmentAssessment(
        company_id=company_id,
        assessed_at=datetime.utcnow(),
        **assessment_data.model_dump()
    )

    db.add(assessment)
    db.commit()
    db.refresh(assessment)

    return assessment


# 2. GET ASSESSMENTS
@router.get(
    "/",
    response_model=list[EnrollmentAssessmentResponse]
)
def get_enrollment_assessments(
    company_id: int,
    enrollment_id: int | None = None,
    db: Session = Depends(get_db)
):
    query = db.query(EnrollmentAssessment).filter(
        EnrollmentAssessment.company_id == company_id
    )

    if enrollment_id is not None:
        query = query.filter(
            EnrollmentAssessment.enrollment_id == enrollment_id
        )

    return query.order_by(
        EnrollmentAssessment.assessed_at.desc()
    ).all()


# 3. GET ONE ASSESSMENT
@router.get(
    "/{assessment_id}",
    response_model=EnrollmentAssessmentResponse
)
def get_enrollment_assessment(
    assessment_id: int,
    company_id: int,
    db: Session = Depends(get_db)
):
    assessment = db.query(EnrollmentAssessment).filter(
        EnrollmentAssessment.assessment_id == assessment_id,
        EnrollmentAssessment.company_id == company_id
    ).first()

    if assessment is None:
        raise HTTPException(
            status_code=404,
            detail="Assessment not found"
        )

    return assessment


# 4. UPDATE ASSESSMENT
@router.put(
    "/{assessment_id}",
    response_model=EnrollmentAssessmentResponse
)
def update_enrollment_assessment(
    assessment_id: int,
    company_id: int,
    assessment_data: EnrollmentAssessmentUpdate,
    db: Session = Depends(get_db)
):
    assessment = db.query(EnrollmentAssessment).filter(
        EnrollmentAssessment.assessment_id == assessment_id,
        EnrollmentAssessment.company_id == company_id
    ).first()

    if assessment is None:
        raise HTTPException(
            status_code=404,
            detail="Assessment not found"
        )

    update_data = assessment_data.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(assessment, field, value)

    db.commit()
    db.refresh(assessment)

    return assessment


# 5. DELETE ASSESSMENT
@router.delete("/{assessment_id}")
def delete_enrollment_assessment(
    assessment_id: int,
    company_id: int,
    db: Session = Depends(get_db)
):
    assessment = db.query(EnrollmentAssessment).filter(
        EnrollmentAssessment.assessment_id == assessment_id,
        EnrollmentAssessment.company_id == company_id
    ).first()

    if assessment is None:
        raise HTTPException(
            status_code=404,
            detail="Assessment not found"
        )

    db.delete(assessment)
    db.commit()

    return {
        "message": "Enrollment assessment deleted successfully"
    }