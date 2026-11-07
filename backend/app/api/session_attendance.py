from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_db

from backend.app.db.employee import Employee
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
    record = db.query(SessionAttendance).filter(
        SessionAttendance.attendance_id == attendance_id,
        SessionAttendance.company_id == company_id
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
    recorded_by: int,
    attendance_data: SessionAttendanceCreate,
    db: Session = Depends(get_db)
):
    session = db.query(CourseSession).filter(
        CourseSession.session_id == attendance_data.session_id,
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
            detail="Cannot record attendance for a cancelled session"
        )

    employee = db.query(Employee).filter(
        Employee.id == attendance_data.employee_id,
        Employee.company_id == company_id,
        Employee.is_active == True
    ).first()

    if employee is None:
        raise HTTPException(
            status_code=404,
            detail="Employee not found in this company"
        )

    recorder = db.query(Employee).filter(
        Employee.id == recorded_by,
        Employee.company_id == company_id,
        Employee.is_active == True
    ).first()

    if recorder is None:
        raise HTTPException(
            status_code=404,
            detail="Recording employee not found in this company"
        )

    enrollment = db.query(Enrollment).filter(
        Enrollment.company_id == company_id,
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

    record = SessionAttendance(
        company_id=company_id,
        session_id=attendance_data.session_id,
        employee_id=attendance_data.employee_id,
        attendance_status=attendance_data.attendance_status,
        attendance_notes=attendance_data.attendance_notes,
        recorded_by=recorded_by
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
    db: Session = Depends(get_db)
):
    query = db.query(SessionAttendance).filter(
        SessionAttendance.company_id == company_id
    )

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
    db: Session = Depends(get_db)
):
    return get_attendance_record(attendance_id, company_id, db)


# 4. UPDATE ATTENDANCE
@router.put("/{attendance_id}", response_model=SessionAttendanceResponse)
def update_attendance(
    attendance_id: int,
    company_id: int,
    attendance_data: SessionAttendanceUpdate,
    db: Session = Depends(get_db)
):
    record = get_attendance_record(attendance_id, company_id, db)

    update_data = attendance_data.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(record, field, value)

    db.commit()
    db.refresh(record)

    return record


# 5. CHECK IN
@router.patch("/{attendance_id}/check-in", response_model=SessionAttendanceResponse)
def check_in(
    attendance_id: int,
    company_id: int,
    recorded_by: int,
    db: Session = Depends(get_db)
):
    record = get_attendance_record(attendance_id, company_id, db)

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

    recorder = db.query(Employee).filter(
        Employee.id == recorded_by,
        Employee.company_id == company_id,
        Employee.is_active == True
    ).first()

    if recorder is None:
        raise HTTPException(
            status_code=404,
            detail="Recording employee not found"
        )

    record.check_in_time = datetime.utcnow()
    record.recorded_by = recorded_by

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
    recorded_by: int,
    db: Session = Depends(get_db)
):
    record = get_attendance_record(attendance_id, company_id, db)

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

    recorder = db.query(Employee).filter(
        Employee.id == recorded_by,
        Employee.company_id == company_id,
        Employee.is_active == True
    ).first()

    if recorder is None:
        raise HTTPException(
            status_code=404,
            detail="Recording employee not found"
        )

    record.check_out_time = datetime.utcnow()
    record.recorded_by = recorded_by

    db.commit()
    db.refresh(record)

    return record