from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_db

from backend.app.db.course import Course
from backend.app.db.course_session import CourseSession
from backend.app.db.employee import Employee

from backend.app.schemas.course_session import (
    CourseSessionCreate,
    CourseSessionUpdate,
    CourseSessionStatusUpdate,
    CourseSessionCompletion,
    CourseSessionCancellation,
    CourseSessionResponse,
)


router = APIRouter(
    prefix="/course-sessions",
    tags=["Course Sessions"]
)


# 1. CREATE COURSE SESSION
@router.post("/", response_model=CourseSessionResponse, status_code=201)
def create_course_session(
    company_id: int,
    session_data: CourseSessionCreate,
    db: Session = Depends(get_db)
):
    course = db.query(Course).filter(
        Course.id == session_data.course_id,
        Course.company_id == company_id,
        Course.is_active == True
    ).first()

    if course is None:
        raise HTTPException(
            status_code=404,
            detail="Active course not found in this company"
        )

    new_session = CourseSession(
        **session_data.model_dump(),
        company_id=company_id,
        session_status="Scheduled"
    )

    db.add(new_session)
    db.commit()
    db.refresh(new_session)

    return new_session


# 2. GET ALL COURSE SESSIONS
@router.get("/", response_model=list[CourseSessionResponse])
def get_course_sessions(
    company_id: int,
    course_id: int | None = None,
    session_status: str | None = None,
    db: Session = Depends(get_db)
):
    query = db.query(CourseSession).filter(
        CourseSession.company_id == company_id
    )

    if course_id is not None:
        query = query.filter(
            CourseSession.course_id == course_id
        )

    if session_status is not None:
        query = query.filter(
            CourseSession.session_status == session_status
        )

    return query.order_by(
        CourseSession.start_datetime
    ).all()


# 3. GET ONE COURSE SESSION
@router.get("/{session_id}", response_model=CourseSessionResponse)
def get_course_session(
    session_id: int,
    company_id: int,
    db: Session = Depends(get_db)
):
    session = db.query(CourseSession).filter(
        CourseSession.session_id == session_id,
        CourseSession.company_id == company_id
    ).first()

    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Course session not found"
        )

    return session


# 4. UPDATE COURSE SESSION
@router.put("/{session_id}", response_model=CourseSessionResponse)
def update_course_session(
    session_id: int,
    company_id: int,
    session_data: CourseSessionUpdate,
    db: Session = Depends(get_db)
):
    session = db.query(CourseSession).filter(
        CourseSession.session_id == session_id,
        CourseSession.company_id == company_id
    ).first()

    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Course session not found"
        )

    if session.session_status in ["Completed", "Cancelled"]:
        raise HTTPException(
            status_code=400,
            detail="Completed or cancelled sessions cannot be edited"
        )

    update_data = session_data.model_dump(exclude_unset=True)

    new_start = update_data.get(
        "start_datetime",
        session.start_datetime
    )
    new_end = update_data.get(
        "end_datetime",
        session.end_datetime
    )
    new_deadline = update_data.get(
        "registration_deadline",
        session.registration_deadline
    )

    if new_end <= new_start:
        raise HTTPException(
            status_code=422,
            detail="End time must be after start time"
        )

    if new_deadline > new_start:
        raise HTTPException(
            status_code=422,
            detail="Registration deadline cannot be after session start"
        )

    for field, value in update_data.items():
        setattr(session, field, value)

    db.commit()
    db.refresh(session)

    return session


# 5. UPDATE SESSION STATUS
@router.patch("/{session_id}/status", response_model=CourseSessionResponse)
def update_session_status(
    session_id: int,
    company_id: int,
    status_data: CourseSessionStatusUpdate,
    db: Session = Depends(get_db)
):
    session = db.query(CourseSession).filter(
        CourseSession.session_id == session_id,
        CourseSession.company_id == company_id
    ).first()

    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Course session not found"
        )

    if session.session_status in ["Completed", "Cancelled"]:
        raise HTTPException(
            status_code=400,
            detail="This session is already finalized"
        )

    session.session_status = status_data.session_status

    db.commit()
    db.refresh(session)

    return session


# 6. RECORD SESSION COMPLETION
@router.put("/{session_id}/completion", response_model=CourseSessionResponse)
def complete_course_session(
    session_id: int,
    company_id: int,
    completion_data: CourseSessionCompletion,
    db: Session = Depends(get_db)
):
    session = db.query(CourseSession).filter(
        CourseSession.session_id == session_id,
        CourseSession.company_id == company_id
    ).first()

    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Course session not found"
        )

    if session.session_status == "Cancelled":
        raise HTTPException(
            status_code=400,
            detail="Cancelled sessions cannot be completed"
        )

    session.completion_status = completion_data.completion_status
    session.completion_date = completion_data.completion_date
    session.completion_notes = completion_data.completion_notes
    session.session_status = "Completed"

    db.commit()
    db.refresh(session)

    return session


# 7. CANCEL COURSE SESSION
@router.put("/{session_id}/cancel", response_model=CourseSessionResponse)
def cancel_course_session(
    session_id: int,
    company_id: int,
    cancelled_by: int,
    cancellation_data: CourseSessionCancellation,
    db: Session = Depends(get_db)
):
    session = db.query(CourseSession).filter(
        CourseSession.session_id == session_id,
        CourseSession.company_id == company_id
    ).first()

    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Course session not found"
        )

    if session.session_status in ["Completed", "Cancelled"]:
        raise HTTPException(
            status_code=400,
            detail="This session is already finalized"
        )

    employee = db.query(Employee).filter(
        Employee.id == cancelled_by,
        Employee.company_id == company_id,
        Employee.is_active == True
    ).first()

    if employee is None:
        raise HTTPException(
            status_code=404,
            detail="Cancelling employee not found in this company"
        )

    session.session_status = "Cancelled"
    session.cancellation_reason = cancellation_data.cancellation_reason
    session.cancelled_at = datetime.now()
    session.cancelled_by = employee.id

    db.commit()
    db.refresh(session)

    return session