from datetime import datetime

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
from backend.app.db.session_attendance import SessionAttendance

from backend.app.schemas.session_attendance import (
    SessionAttendanceCreate,
    SessionAttendanceUpdate,
    SessionAttendanceResponse,
)


router = APIRouter(
    prefix="/session-attendance",
    tags=["Session Attendance"]
)


def get_attendance_record(
    attendance_id: int,
    company_id: int,
    db: Session
):
    record = db.query(SessionAttendance).join(
        CourseSession,
        SessionAttendance.session_id == CourseSession.session_id,
    ).join(
        Course,
        CourseSession.course_id == Course.id,
    ).join(
        Employee,
        SessionAttendance.employee_id == Employee.id,
    ).filter(
        SessionAttendance.attendance_id == attendance_id,
        SessionAttendance.company_id == company_id,
        CourseSession.company_id == company_id,
        Course.company_id == company_id,
        Employee.company_id == company_id,
    ).first()

    if record is None:
        raise HTTPException(
            status_code=404,
            detail="Attendance record not found"
        )

    return record


# 1. RECORD ATTENDANCE
@router.post("/", response_model=SessionAttendanceResponse, status_code=201)
def create_attendance(
    company_id: int,
    attendance_data: SessionAttendanceCreate,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    session = db.query(CourseSession).join(
        Course,
        CourseSession.course_id == Course.id,
    ).filter(
        CourseSession.session_id == attendance_data.session_id,
        CourseSession.company_id == company_id,
        Course.company_id == company_id,
    ).first()

    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Course session not found"
        )

    if session.session_status == "Cancelled":
        raise HTTPException(
            status_code=400,
            detail="Cannot record attendance for a cancelled session"
        )

    employee = ensure_employee_access(
        context,
        db,
        attendance_data.employee_id,
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
        Enrollment.session_id == attendance_data.session_id,
        Enrollment.employee_id == attendance_data.employee_id,
        Enrollment.status.in_(["Approved", "In Progress", "Completed"])
    ).first()

    if enrollment is None:
        raise HTTPException(
            status_code=400,
            detail="Employee must have an approved enrollment for this session"
        )

    existing = db.query(SessionAttendance).filter(
        SessionAttendance.session_id == attendance_data.session_id,
        SessionAttendance.employee_id == attendance_data.employee_id
    ).first()

    if existing:
        raise HTTPException(
            status_code=409,
            detail="Attendance has already been recorded for this employee"
        )

    actor = get_membership_employee(context, db, required=False)
    record = SessionAttendance(
        company_id=company_id,
        session_id=attendance_data.session_id,
        employee_id=attendance_data.employee_id,
        attendance_status=attendance_data.attendance_status,
        attendance_notes=attendance_data.attendance_notes,
        recorded_by=actor.id if actor else None,
        recorded_by_user_id=context.user.user_id,
    )

    db.add(record)
    db.commit()
    db.refresh(record)

    return record


# 2. GET ATTENDANCE RECORDS
@router.get("/", response_model=list[SessionAttendanceResponse])
def get_attendance_records(
    company_id: int,
    session_id: int | None = None,
    employee_id: int | None = None,
    attendance_status: str | None = None,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    query = db.query(SessionAttendance).join(
        CourseSession,
        SessionAttendance.session_id == CourseSession.session_id,
    ).join(
        Course,
        CourseSession.course_id == Course.id,
    ).join(
        Employee,
        SessionAttendance.employee_id == Employee.id,
    ).filter(
        SessionAttendance.company_id == company_id,
        CourseSession.company_id == company_id,
        Course.company_id == company_id,
        Employee.company_id == company_id,
    )
    employee_ids = allowed_employee_ids(context, db)
    if employee_ids is not None:
        query = query.filter(SessionAttendance.employee_id.in_(employee_ids))

    if session_id is not None:
        query = query.filter(
            SessionAttendance.session_id == session_id
        )

    if employee_id is not None:
        query = query.filter(
            SessionAttendance.employee_id == employee_id
        )

    if attendance_status is not None:
        query = query.filter(
            SessionAttendance.attendance_status == attendance_status
        )

    return query.order_by(
        SessionAttendance.attendance_id.desc()
    ).all()


# 3. GET ONE ATTENDANCE RECORD
@router.get("/{attendance_id}", response_model=SessionAttendanceResponse)
def get_attendance(
    attendance_id: int,
    company_id: int,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    record = get_attendance_record(attendance_id, company_id, db)
    ensure_employee_access(context, db, record.employee_id)
    return record


# 4. UPDATE ATTENDANCE
@router.put("/{attendance_id}", response_model=SessionAttendanceResponse)
def update_attendance(
    attendance_id: int,
    company_id: int,
    attendance_data: SessionAttendanceUpdate,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    record = get_attendance_record(attendance_id, company_id, db)
    ensure_employee_access(context, db, record.employee_id)

    update_data = attendance_data.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(record, field, value)

    actor = get_membership_employee(context, db, required=False)
    record.recorded_by = actor.id if actor else None
    record.recorded_by_user_id = context.user.user_id
    db.commit()
    db.refresh(record)

    return record


# 5. CHECK IN
@router.patch("/{attendance_id}/check-in", response_model=SessionAttendanceResponse)
def check_in(
    attendance_id: int,
    company_id: int,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    record = get_attendance_record(attendance_id, company_id, db)
    ensure_employee_access(context, db, record.employee_id)

    if record.attendance_status in ["Absent", "Excused"]:
        raise HTTPException(
            status_code=400,
            detail="Cannot check in an absent or excused employee"
        )

    if record.check_in_time is not None:
        raise HTTPException(
            status_code=400,
            detail="Employee has already checked in"
        )

    record.check_in_time = datetime.utcnow()
    actor = get_membership_employee(context, db, required=False)
    record.recorded_by = actor.id if actor else None
    record.recorded_by_user_id = context.user.user_id

    if record.attendance_status == "Pending":
        record.attendance_status = "Present"

    db.commit()
    db.refresh(record)

    return record


# 6. CHECK OUT
@router.patch("/{attendance_id}/check-out", response_model=SessionAttendanceResponse)
def check_out(
    attendance_id: int,
    company_id: int,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    record = get_attendance_record(attendance_id, company_id, db)
    ensure_employee_access(context, db, record.employee_id)

    if record.check_in_time is None:
        raise HTTPException(
            status_code=400,
            detail="Employee must check in before checking out"
        )

    if record.check_out_time is not None:
        raise HTTPException(
            status_code=400,
            detail="Employee has already checked out"
        )

    record.check_out_time = datetime.utcnow()
    actor = get_membership_employee(context, db, required=False)
    record.recorded_by = actor.id if actor else None
    record.recorded_by_user_id = context.user.user_id

    db.commit()
    db.refresh(record)

    return record