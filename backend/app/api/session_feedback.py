from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_db

from backend.app.db.employee import Employee
from backend.app.db.course_session import CourseSession
from backend.app.db.enrollment import Enrollment
from backend.app.db.session_feedback import SessionFeedback

from backend.app.schemas.session_feedback import (
    SessionFeedbackCreate,
    SessionFeedbackUpdate,
    SessionFeedbackResponse,
)


router = APIRouter(
    prefix="/session-feedback",
    tags=["Session Feedback"]
)


# 1. SUBMIT FEEDBACK
@router.post("/", response_model=SessionFeedbackResponse, status_code=201)
def create_session_feedback(
    company_id: int,
    employee_id: int,
    feedback_data: SessionFeedbackCreate,
    db: Session = Depends(get_db)
):
    employee = db.query(Employee).filter(
        Employee.id == employee_id,
        Employee.company_id == company_id,
        Employee.is_active == True
    ).first()

    if employee is None:
        raise HTTPException(
            status_code=404,
            detail="Employee not found in this company"
        )

    session = db.query(CourseSession).filter(
        CourseSession.session_id == feedback_data.session_id,
        CourseSession.company_id == company_id
    ).first()

    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Course session not found"
        )

    if session.session_status != "Completed":
        raise HTTPException(
            status_code=400,
            detail="Feedback can only be submitted after session completion"
        )

    enrollment = db.query(Enrollment).filter(
        Enrollment.company_id == company_id,
        Enrollment.employee_id == employee_id,
        Enrollment.session_id == feedback_data.session_id,
        Enrollment.status == "Completed"
    ).first()

    if enrollment is None:
        raise HTTPException(
            status_code=400,
            detail="Only employees who completed the session can submit feedback"
        )

    existing = db.query(SessionFeedback).filter(
        SessionFeedback.session_id == feedback_data.session_id,
        SessionFeedback.employee_id == employee_id
    ).first()

    if existing:
        raise HTTPException(
            status_code=409,
            detail="Feedback has already been submitted for this session"
        )

    feedback = SessionFeedback(
        company_id=company_id,
        employee_id=employee_id,
        **feedback_data.model_dump()
    )

    db.add(feedback)
    db.commit()
    db.refresh(feedback)

    return feedback


# 2. GET FEEDBACK RECORDS
@router.get("/", response_model=list[SessionFeedbackResponse])
def get_session_feedback(
    company_id: int,
    session_id: int | None = None,
    employee_id: int | None = None,
    db: Session = Depends(get_db)
):
    query = db.query(SessionFeedback).filter(
        SessionFeedback.company_id == company_id
    )

    if session_id is not None:
        query = query.filter(
            SessionFeedback.session_id == session_id
        )

    if employee_id is not None:
        query = query.filter(
            SessionFeedback.employee_id == employee_id
        )

    return query.order_by(
        SessionFeedback.submitted_at.desc()
    ).all()


# 3. GET ONE FEEDBACK RECORD
@router.get("/{feedback_id}", response_model=SessionFeedbackResponse)
def get_feedback(
    feedback_id: int,
    company_id: int,
    db: Session = Depends(get_db)
):
    feedback = db.query(SessionFeedback).filter(
        SessionFeedback.feedback_id == feedback_id,
        SessionFeedback.company_id == company_id
    ).first()

    if feedback is None:
        raise HTTPException(
            status_code=404,
            detail="Feedback record not found"
        )

    return feedback


# 4. UPDATE FEEDBACK
@router.put("/{feedback_id}", response_model=SessionFeedbackResponse)
def update_feedback(
    feedback_id: int,
    company_id: int,
    employee_id: int,
    feedback_data: SessionFeedbackUpdate,
    db: Session = Depends(get_db)
):
    feedback = db.query(SessionFeedback).filter(
        SessionFeedback.feedback_id == feedback_id,
        SessionFeedback.company_id == company_id,
        SessionFeedback.employee_id == employee_id
    ).first()

    if feedback is None:
        raise HTTPException(
            status_code=404,
            detail="Feedback record not found for this employee"
        )

    update_data = feedback_data.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(feedback, field, value)

    db.commit()
    db.refresh(feedback)

    return feedback