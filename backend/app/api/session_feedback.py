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

from backend.app.db.employee import Employee
from backend.app.db.course import Course
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


def _feedback_query(db: Session, company_id: int):
    return db.query(SessionFeedback).join(
        CourseSession,
        SessionFeedback.session_id == CourseSession.session_id,
    ).join(
        Course,
        CourseSession.course_id == Course.id,
    ).join(
        Employee,
        SessionFeedback.employee_id == Employee.id,
    ).filter(
        SessionFeedback.company_id == company_id,
        CourseSession.company_id == company_id,
        Course.company_id == company_id,
        Employee.company_id == company_id,
    )


# 1. SUBMIT FEEDBACK
@router.post("/", response_model=SessionFeedbackResponse, status_code=201)
def create_session_feedback(
    company_id: int,
    employee_id: int,
    feedback_data: SessionFeedbackCreate,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    if context.role == "Employee":
        employee_id = get_membership_employee(context, db).id
    employee = ensure_employee_access(context, db, employee_id)

    session = db.query(CourseSession).join(
        Course,
        CourseSession.course_id == Course.id,
    ).filter(
        CourseSession.session_id == feedback_data.session_id,
        CourseSession.company_id == company_id,
        Course.company_id == company_id,
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

    enrollment = db.query(Enrollment).join(
        CourseSession,
        Enrollment.session_id == CourseSession.session_id,
    ).join(
        Course,
        CourseSession.course_id == Course.id,
    ).filter(
        Enrollment.company_id == company_id,
        CourseSession.company_id == company_id,
        Course.company_id == company_id,
        Enrollment.course_id == Course.id,
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
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    query = _feedback_query(db, company_id)
    employee_ids = allowed_employee_ids(context, db)
    if employee_ids is not None:
        query = query.filter(SessionFeedback.employee_id.in_(employee_ids))

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
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    feedback = _feedback_query(db, company_id).filter(
        SessionFeedback.feedback_id == feedback_id,
    ).first()

    if feedback is None:
        raise HTTPException(
            status_code=404,
            detail="Feedback record not found"
        )

    ensure_employee_access(context, db, feedback.employee_id)
    return feedback


# 4. UPDATE FEEDBACK
@router.put("/{feedback_id}", response_model=SessionFeedbackResponse)
def update_feedback(
    feedback_id: int,
    company_id: int,
    employee_id: int,
    feedback_data: SessionFeedbackUpdate,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    if context.role == "Employee":
        employee_id = get_membership_employee(context, db).id
    ensure_employee_access(context, db, employee_id)
    feedback = _feedback_query(db, company_id).filter(
        SessionFeedback.feedback_id == feedback_id,
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