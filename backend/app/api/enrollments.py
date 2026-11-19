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


def _enrollment_query(db: Session, company_id: int):
    return db.query(Enrollment).join(
        Employee,
        Enrollment.employee_id == Employee.id,
    ).join(
        CourseSession,
        Enrollment.session_id == CourseSession.session_id,
    ).join(
        Course,
        CourseSession.course_id == Course.id,
    ).filter(
        Enrollment.company_id == company_id,
        Employee.company_id == company_id,
        CourseSession.company_id == company_id,
        Course.company_id == company_id,
        Enrollment.course_id == Course.id,
    )


# 1. REQUEST ENROLLMENT
@router.post("/", response_model=EnrollmentResponse, status_code=201)
def create_enrollment(
    company_id: int,
    enrollment_data: EnrollmentCreate,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    employee = ensure_employee_access(
        context,
        db,
        enrollment_data.employee_id,
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
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    query = _enrollment_query(db, company_id)
    employee_ids = allowed_employee_ids(context, db)
    if employee_ids is not None:
        query = query.filter(Enrollment.employee_id.in_(employee_ids))

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
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    enrollment = _enrollment_query(db, company_id).filter(
        Enrollment.enrollment_id == enrollment_id,
        Enrollment.company_id == company_id
    ).first()

    if enrollment is None:
        raise HTTPException(
            status_code=404,
            detail="Enrollment not found"
        )

    ensure_employee_access(context, db, enrollment.employee_id)
    return enrollment


# 4. APPROVE OR REJECT ENROLLMENT
@router.put("/{enrollment_id}/approval", response_model=EnrollmentResponse)
def review_enrollment(
    enrollment_id: int,
    company_id: int,
    approval_data: EnrollmentApproval,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    enrollment = _enrollment_query(db, company_id).filter(
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

    enrollment.approval_status = approval_data.approval_status
    approver = get_membership_employee(context, db, required=False)
    enrollment.approved_by = approver.id if approver else None
    enrollment.approved_by_user_id = context.user.user_id
    enrollment.approval_date = datetime.utcnow()
    enrollment.approval_comments = approval_data.approval_comments

    if approval_data.approval_status == "Approved":
        enrollment.status = "Approved"
    else:
        enrollment.status = "Rejected"

    enrollment.status_updated_by = approver.id if approver else None
    enrollment.status_updated_by_user_id = context.user.user_id

    db.commit()
    db.refresh(enrollment)

    return enrollment


# 5. START ENROLLMENT
@router.patch("/{enrollment_id}/start", response_model=EnrollmentResponse)
def start_enrollment(
    enrollment_id: int,
    company_id: int,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    enrollment = _enrollment_query(db, company_id).filter(
        Enrollment.enrollment_id == enrollment_id,
        Enrollment.company_id == company_id
    ).first()

    if enrollment is None:
        raise HTTPException(
            status_code=404,
            detail="Enrollment not found"
        )

    ensure_employee_access(context, db, enrollment.employee_id)
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
    actor = get_membership_employee(context, db, required=False)
    enrollment.status_updated_by = actor.id if actor else None
    enrollment.status_updated_by_user_id = context.user.user_id

    db.commit()
    db.refresh(enrollment)

    return enrollment


# 6. UPDATE ENROLLMENT PROGRESS
@router.patch("/{enrollment_id}/progress", response_model=EnrollmentResponse)
def update_enrollment_progress(
    enrollment_id: int,
    company_id: int,
    progress_data: EnrollmentProgressUpdate,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    enrollment = _enrollment_query(db, company_id).filter(
        Enrollment.enrollment_id == enrollment_id,
        Enrollment.company_id == company_id
    ).first()

    if enrollment is None:
        raise HTTPException(
            status_code=404,
            detail="Enrollment not found"
        )

    ensure_employee_access(context, db, enrollment.employee_id)
    if enrollment.status != "In Progress":
        raise HTTPException(
            status_code=400,
            detail="Progress can only be updated for active enrollments"
        )

    enrollment.progress_percentage = progress_data.progress_percentage
    enrollment.last_activity_at = datetime.utcnow()
    actor = get_membership_employee(context, db, required=False)
    enrollment.status_updated_by = actor.id if actor else None
    enrollment.status_updated_by_user_id = context.user.user_id

    db.commit()
    db.refresh(enrollment)

    return enrollment


# 7. COMPLETE ENROLLMENT
@router.patch("/{enrollment_id}/complete", response_model=EnrollmentResponse)
def complete_enrollment(
    enrollment_id: int,
    company_id: int,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    enrollment = _enrollment_query(db, company_id).filter(
        Enrollment.enrollment_id == enrollment_id,
        Enrollment.company_id == company_id
    ).first()

    if enrollment is None:
        raise HTTPException(
            status_code=404,
            detail="Enrollment not found"
        )

    ensure_employee_access(context, db, enrollment.employee_id)
    if enrollment.status != "In Progress":
        raise HTTPException(
            status_code=400,
            detail="Only in-progress enrollments can be completed"
        )

    enrollment.status = "Completed"
    enrollment.progress_percentage = 100
    enrollment.completed_at = datetime.utcnow()
    enrollment.last_activity_at = datetime.utcnow()
    actor = get_membership_employee(context, db, required=False)
    enrollment.status_updated_by = actor.id if actor else None
    enrollment.status_updated_by_user_id = context.user.user_id

    db.commit()
    db.refresh(enrollment)

    return enrollment


# 8. WITHDRAW FROM ENROLLMENT
@router.patch("/{enrollment_id}/withdraw", response_model=EnrollmentResponse)
def withdraw_enrollment(
    enrollment_id: int,
    company_id: int,
    withdrawal_data: EnrollmentWithdrawal,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    enrollment = _enrollment_query(db, company_id).filter(
        Enrollment.enrollment_id == enrollment_id,
        Enrollment.company_id == company_id
    ).first()

    if enrollment is None:
        raise HTTPException(
            status_code=404,
            detail="Enrollment not found"
        )

    ensure_employee_access(context, db, enrollment.employee_id)
    if enrollment.status in ["Completed", "Withdrawn", "Rejected", "Failed"]:
        raise HTTPException(
            status_code=400,
            detail="This enrollment cannot be withdrawn"
        )

    actor = get_membership_employee(context, db, required=False)
    enrollment.status = "Withdrawn"
    enrollment.withdrawn_at = datetime.utcnow()
    enrollment.withdrawal_reason = withdrawal_data.withdrawal_reason
    enrollment.status_updated_by = actor.id if actor else None
    enrollment.status_updated_by_user_id = context.user.user_id

    db.commit()
    db.refresh(enrollment)

    return enrollment


# 9. MARK ENROLLMENT AS FAILED
@router.patch("/{enrollment_id}/fail", response_model=EnrollmentResponse)
def fail_enrollment(
    enrollment_id: int,
    company_id: int,
    failure_data: EnrollmentFailure,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    enrollment = _enrollment_query(db, company_id).filter(
        Enrollment.enrollment_id == enrollment_id,
        Enrollment.company_id == company_id
    ).first()

    if enrollment is None:
        raise HTTPException(
            status_code=404,
            detail="Enrollment not found"
        )

    ensure_employee_access(context, db, enrollment.employee_id)
    if enrollment.status not in ["Approved", "In Progress"]:
        raise HTTPException(
            status_code=400,
            detail="Only approved or in-progress enrollments can be failed"
        )

    actor = get_membership_employee(context, db, required=False)
    enrollment.status = "Failed"
    enrollment.failure_reason = failure_data.failure_reason
    enrollment.status_updated_by = actor.id if actor else None
    enrollment.status_updated_by_user_id = context.user.user_id

    db.commit()
    db.refresh(enrollment)

    return enrollment