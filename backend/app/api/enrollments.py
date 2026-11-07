from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_db

from backend.app.db.employee import Employee
from backend.app.db.course import Course
from backend.app.db.course_session import CourseSession
from backend.app.db.enrollment import Enrollment

from backend.app.schemas.enrollment import (
    EnrollmentCreate,
    EnrollmentApproval,
    EnrollmentProgressUpdate,
    EnrollmentWithdrawal,
    EnrollmentFailure,
    EnrollmentResponse,
)


router = APIRouter(
    prefix="/enrollments",
    tags=["Enrollments"]
)


# 1. REQUEST ENROLLMENT
@router.post("/", response_model=EnrollmentResponse, status_code=201)
def create_enrollment(
    company_id: int,
    enrollment_data: EnrollmentCreate,
    db: Session = Depends(get_db)
):
    employee = db.query(Employee).filter(
        Employee.id == enrollment_data.employee_id,
        Employee.company_id == company_id,
        Employee.is_active == True
    ).first()

    if employee is None:
        raise HTTPException(
            status_code=404,
            detail="Employee not found in this company"
        )

    session = db.query(CourseSession).filter(
        CourseSession.session_id == enrollment_data.session_id,
        CourseSession.company_id == company_id
    ).first()

    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Course session not found"
        )

    if session.session_status != "Scheduled":
        raise HTTPException(
            status_code=400,
            detail="Enrollment is only available for scheduled sessions"
        )

    if datetime.now() > session.registration_deadline:
        raise HTTPException(
            status_code=400,
            detail="Registration deadline has passed"
        )

    course = db.query(Course).filter(
        Course.id == session.course_id,
        Course.company_id == company_id,
        Course.is_active == True
    ).first()

    if course is None:
        raise HTTPException(
            status_code=404,
            detail="Active course not found"
        )

    if (
        enrollment_data.expected_completion_date
        and enrollment_data.expected_completion_date < session.end_datetime
    ):
        raise HTTPException(
            status_code=422,
            detail="Expected completion cannot be before the session ends"
        )

    existing = db.query(Enrollment).filter(
        Enrollment.company_id == company_id,
        Enrollment.employee_id == enrollment_data.employee_id,
        Enrollment.session_id == enrollment_data.session_id,
        Enrollment.status.notin_(["Withdrawn", "Rejected", "Failed"])
    ).first()

    if existing:
        raise HTTPException(
            status_code=409,
            detail="Employee already has an active enrollment for this session"
        )

    if session.max_participants is not None:
        occupied = db.query(Enrollment).filter(
            Enrollment.company_id == company_id,
            Enrollment.session_id == session.session_id,
            Enrollment.status.in_(["Pending Approval", "Approved", "In Progress", "Completed"])
        ).count()

        if occupied >= session.max_participants:
            raise HTTPException(
                status_code=400,
                detail="Course session has reached its participant limit"
            )

    enrollment = Enrollment(
        company_id=company_id,
        employee_id=employee.id,
        course_id=course.id,
        session_id=session.session_id,
        expected_completion_date=enrollment_data.expected_completion_date,
        status="Pending Approval",
        approval_status="Pending",
        progress_percentage=0
    )

    db.add(enrollment)
    db.commit()
    db.refresh(enrollment)

    return enrollment


# 2. GET ENROLLMENTS
@router.get("/", response_model=list[EnrollmentResponse])
def get_enrollments(
    company_id: int,
    employee_id: int | None = None,
    session_id: int | None = None,
    status: str | None = None,
    approval_status: str | None = None,
    db: Session = Depends(get_db)
):
    query = db.query(Enrollment).filter(
        Enrollment.company_id == company_id
    )

    if employee_id is not None:
        query = query.filter(
            Enrollment.employee_id == employee_id
        )

    if session_id is not None:
        query = query.filter(
            Enrollment.session_id == session_id
        )

    if status is not None:
        query = query.filter(
            Enrollment.status == status
        )

    if approval_status is not None:
        query = query.filter(
            Enrollment.approval_status == approval_status
        )

    return query.order_by(
        Enrollment.enrollment_id.desc()
    ).all()


# 3. GET ONE ENROLLMENT
@router.get("/{enrollment_id}", response_model=EnrollmentResponse)
def get_enrollment(
    enrollment_id: int,
    company_id: int,
    db: Session = Depends(get_db)
):
    enrollment = db.query(Enrollment).filter(
        Enrollment.enrollment_id == enrollment_id,
        Enrollment.company_id == company_id
    ).first()

    if enrollment is None:
        raise HTTPException(
            status_code=404,
            detail="Enrollment not found"
        )

    return enrollment


# 4. APPROVE OR REJECT ENROLLMENT
@router.put("/{enrollment_id}/approval", response_model=EnrollmentResponse)
def review_enrollment(
    enrollment_id: int,
    company_id: int,
    approved_by: int,
    approval_data: EnrollmentApproval,
    db: Session = Depends(get_db)
):
    enrollment = db.query(Enrollment).filter(
        Enrollment.enrollment_id == enrollment_id,
        Enrollment.company_id == company_id
    ).first()

    if enrollment is None:
        raise HTTPException(
            status_code=404,
            detail="Enrollment not found"
        )

    if enrollment.approval_status != "Pending":
        raise HTTPException(
            status_code=400,
            detail="This enrollment has already been reviewed"
        )

    approver = db.query(Employee).filter(
        Employee.id == approved_by,
        Employee.company_id == company_id,
        Employee.is_active == True
    ).first()

    if approver is None:
        raise HTTPException(
            status_code=404,
            detail="Approving employee not found in this company"
        )

    enrollment.approval_status = approval_data.approval_status
    enrollment.approved_by = approved_by
    enrollment.approval_date = datetime.utcnow()
    enrollment.approval_comments = approval_data.approval_comments

    if approval_data.approval_status == "Approved":
        enrollment.status = "Approved"
    else:
        enrollment.status = "Rejected"

    enrollment.status_updated_by = approved_by

    db.commit()
    db.refresh(enrollment)

    return enrollment


# 5. START ENROLLMENT
@router.patch("/{enrollment_id}/start", response_model=EnrollmentResponse)
def start_enrollment(
    enrollment_id: int,
    company_id: int,
    db: Session = Depends(get_db)
):
    enrollment = db.query(Enrollment).filter(
        Enrollment.enrollment_id == enrollment_id,
        Enrollment.company_id == company_id
    ).first()

    if enrollment is None:
        raise HTTPException(
            status_code=404,
            detail="Enrollment not found"
        )

    if enrollment.approval_status != "Approved":
        raise HTTPException(
            status_code=400,
            detail="Enrollment must be approved before starting"
        )

    if enrollment.status != "Approved":
        raise HTTPException(
            status_code=400,
            detail="Only approved enrollments can be started"
        )

    enrollment.status = "In Progress"
    enrollment.started_at = datetime.utcnow()
    enrollment.last_activity_at = datetime.utcnow()

    db.commit()
    db.refresh(enrollment)

    return enrollment


# 6. UPDATE ENROLLMENT PROGRESS
@router.patch("/{enrollment_id}/progress", response_model=EnrollmentResponse)
def update_enrollment_progress(
    enrollment_id: int,
    company_id: int,
    progress_data: EnrollmentProgressUpdate,
    db: Session = Depends(get_db)
):
    enrollment = db.query(Enrollment).filter(
        Enrollment.enrollment_id == enrollment_id,
        Enrollment.company_id == company_id
    ).first()

    if enrollment is None:
        raise HTTPException(
            status_code=404,
            detail="Enrollment not found"
        )

    if enrollment.status != "In Progress":
        raise HTTPException(
            status_code=400,
            detail="Progress can only be updated for active enrollments"
        )

    enrollment.progress_percentage = progress_data.progress_percentage
    enrollment.last_activity_at = datetime.utcnow()

    db.commit()
    db.refresh(enrollment)

    return enrollment


# 7. COMPLETE ENROLLMENT
@router.patch("/{enrollment_id}/complete", response_model=EnrollmentResponse)
def complete_enrollment(
    enrollment_id: int,
    company_id: int,
    db: Session = Depends(get_db)
):
    enrollment = db.query(Enrollment).filter(
        Enrollment.enrollment_id == enrollment_id,
        Enrollment.company_id == company_id
    ).first()

    if enrollment is None:
        raise HTTPException(
            status_code=404,
            detail="Enrollment not found"
        )

    if enrollment.status != "In Progress":
        raise HTTPException(
            status_code=400,
            detail="Only in-progress enrollments can be completed"
        )

    enrollment.status = "Completed"
    enrollment.progress_percentage = 100
    enrollment.completed_at = datetime.utcnow()
    enrollment.last_activity_at = datetime.utcnow()

    db.commit()
    db.refresh(enrollment)

    return enrollment


# 8. WITHDRAW FROM ENROLLMENT
@router.patch("/{enrollment_id}/withdraw", response_model=EnrollmentResponse)
def withdraw_enrollment(
    enrollment_id: int,
    company_id: int,
    status_updated_by: int,
    withdrawal_data: EnrollmentWithdrawal,
    db: Session = Depends(get_db)
):
    enrollment = db.query(Enrollment).filter(
        Enrollment.enrollment_id == enrollment_id,
        Enrollment.company_id == company_id
    ).first()

    if enrollment is None:
        raise HTTPException(
            status_code=404,
            detail="Enrollment not found"
        )

    if enrollment.status in ["Completed", "Withdrawn", "Rejected", "Failed"]:
        raise HTTPException(
            status_code=400,
            detail="This enrollment cannot be withdrawn"
        )

    employee = db.query(Employee).filter(
        Employee.id == status_updated_by,
        Employee.company_id == company_id,
        Employee.is_active == True
    ).first()

    if employee is None:
        raise HTTPException(
            status_code=404,
            detail="Employee not found in this company"
        )

    enrollment.status = "Withdrawn"
    enrollment.withdrawn_at = datetime.utcnow()
    enrollment.withdrawal_reason = withdrawal_data.withdrawal_reason
    enrollment.status_updated_by = status_updated_by

    db.commit()
    db.refresh(enrollment)

    return enrollment


# 9. MARK ENROLLMENT AS FAILED
@router.patch("/{enrollment_id}/fail", response_model=EnrollmentResponse)
def fail_enrollment(
    enrollment_id: int,
    company_id: int,
    status_updated_by: int,
    failure_data: EnrollmentFailure,
    db: Session = Depends(get_db)
):
    enrollment = db.query(Enrollment).filter(
        Enrollment.enrollment_id == enrollment_id,
        Enrollment.company_id == company_id
    ).first()

    if enrollment is None:
        raise HTTPException(
            status_code=404,
            detail="Enrollment not found"
        )

    if enrollment.status not in ["Approved", "In Progress"]:
        raise HTTPException(
            status_code=400,
            detail="Only approved or in-progress enrollments can be failed"
        )

    employee = db.query(Employee).filter(
        Employee.id == status_updated_by,
        Employee.company_id == company_id,
        Employee.is_active == True
    ).first()

    if employee is None:
        raise HTTPException(
            status_code=404,
            detail="Employee not found in this company"
        )

    enrollment.status = "Failed"
    enrollment.failure_reason = failure_data.failure_reason
    enrollment.status_updated_by = status_updated_by

    db.commit()
    db.refresh(enrollment)

    return enrollment