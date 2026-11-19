from datetime import date, datetime

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

from backend.app.db.training_plan import TrainingPlan
from backend.app.db.employee import Employee

from backend.app.schemas.training_plan import (
    TrainingPlanCreate,
    TrainingPlanUpdate,
    TrainingPlanApproval,
    TrainingPlanReview,
    TrainingPlanResponse,
)


router = APIRouter(
    prefix="/training-plans",
    tags=["Training Plans"]
)


def _plan_query(db: Session, company_id: int):
    return db.query(TrainingPlan).join(
        Employee,
        TrainingPlan.employee_id == Employee.id,
    ).filter(
        TrainingPlan.company_id == company_id,
        Employee.company_id == company_id,
    )


# 1. CREATE TRAINING PLAN
@router.post("/", response_model=TrainingPlanResponse, status_code=201)
def create_training_plan(
    company_id: int,
    plan_data: TrainingPlanCreate,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    ensure_employee_access(context, db, plan_data.employee_id)
    creator = get_membership_employee(context, db, required=False)

    new_plan = TrainingPlan(
        **plan_data.model_dump(),
        company_id=company_id,
        created_by=creator.id if creator else None,
        created_by_user_id=context.user.user_id,
        plan_status="Draft",
        approval_status="Pending"
    )

    db.add(new_plan)
    db.commit()
    db.refresh(new_plan)

    return new_plan


# 2. GET TRAINING PLANS
@router.get("/", response_model=list[TrainingPlanResponse])
def get_training_plans(
    company_id: int,
    employee_id: int | None = None,
    plan_status: str | None = None,
    approval_status: str | None = None,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    query = _plan_query(db, company_id)
    employee_ids = allowed_employee_ids(context, db)
    if employee_ids is not None:
        query = query.filter(TrainingPlan.employee_id.in_(employee_ids))

    if employee_id is not None:
        query = query.filter(
            TrainingPlan.employee_id == employee_id
        )

    if plan_status is not None:
        query = query.filter(
            TrainingPlan.plan_status == plan_status
        )

    if approval_status is not None:
        query = query.filter(
            TrainingPlan.approval_status == approval_status
        )

    return query.order_by(
        TrainingPlan.created_at.desc()
    ).all()


# 3. GET ONE TRAINING PLAN
@router.get("/{plan_id}", response_model=TrainingPlanResponse)
def get_training_plan(
    plan_id: int,
    company_id: int,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    plan = _plan_query(db, company_id).filter(
        TrainingPlan.plan_id == plan_id,
    ).first()

    if plan is None:
        raise HTTPException(
            status_code=404,
            detail="Training plan not found"
        )

    ensure_employee_access(context, db, plan.employee_id)
    return plan


# 4. UPDATE DRAFT TRAINING PLAN
@router.put("/{plan_id}", response_model=TrainingPlanResponse)
def update_training_plan(
    plan_id: int,
    company_id: int,
    plan_data: TrainingPlanUpdate,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    plan = _plan_query(db, company_id).filter(
        TrainingPlan.plan_id == plan_id,
    ).first()

    if plan is None:
        raise HTTPException(
            status_code=404,
            detail="Training plan not found"
        )

    ensure_employee_access(context, db, plan.employee_id)
    if plan.plan_status != "Draft":
        raise HTTPException(
            status_code=400,
            detail="Only draft plans can be edited"
        )

    update_data = plan_data.model_dump(exclude_unset=True)

    new_start = update_data.get(
        "plan_start_date",
        plan.plan_start_date
    )
    new_target = update_data.get(
        "target_completion_date",
        plan.target_completion_date
    )

    if new_start and new_target and new_target < new_start:
        raise HTTPException(
            status_code=422,
            detail="Target completion date cannot be before start date"
        )

    for field, value in update_data.items():
        setattr(plan, field, value)

    db.commit()
    db.refresh(plan)

    return plan


# 5. APPROVE OR REJECT TRAINING PLAN
@router.put("/{plan_id}/approval", response_model=TrainingPlanResponse)
def review_training_plan_approval(
    plan_id: int,
    company_id: int,
    approval_data: TrainingPlanApproval,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    plan = _plan_query(db, company_id).filter(
        TrainingPlan.plan_id == plan_id,
    ).first()

    if plan is None:
        raise HTTPException(
            status_code=404,
            detail="Training plan not found"
        )

    ensure_employee_access(context, db, plan.employee_id)
    if plan.plan_status != "Draft":
        raise HTTPException(
            status_code=400,
            detail="Only draft plans can be approved or rejected"
        )

    approver = get_membership_employee(context, db, required=False)
    if approval_data.approval_status == "Approved":
        plan.plan_status = "Approved"
    else:
        plan.plan_status = "Draft"

    plan.approval_status = approval_data.approval_status
    plan.approved_by = approver.id if approver else None
    plan.approved_by_user_id = context.user.user_id
    plan.status_updated_by = approver.id if approver else None
    plan.status_updated_by_user_id = context.user.user_id
    plan.approval_date = datetime.utcnow()
    plan.approval_comments = approval_data.approval_comments

    db.commit()
    db.refresh(plan)

    return plan


# 6. ACTIVATE APPROVED TRAINING PLAN
@router.patch("/{plan_id}/activate", response_model=TrainingPlanResponse)
def activate_training_plan(
    plan_id: int,
    company_id: int,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    plan = _plan_query(db, company_id).filter(
        TrainingPlan.plan_id == plan_id,
    ).first()

    if plan is None:
        raise HTTPException(
            status_code=404,
            detail="Training plan not found"
        )

    ensure_employee_access(context, db, plan.employee_id)
    if plan.approval_status != "Approved":
        raise HTTPException(
            status_code=400,
            detail="Only approved plans can be activated"
        )

    if plan.plan_status != "Approved":
        raise HTTPException(
            status_code=400,
            detail="Plan must be in Approved status before activation"
        )

    plan.plan_status = "Active"
    actor = get_membership_employee(context, db, required=False)
    plan.status_updated_by = actor.id if actor else None
    plan.status_updated_by_user_id = context.user.user_id

    db.commit()
    db.refresh(plan)

    return plan


# 7. RECORD TRAINING PLAN COMPLETION
@router.patch("/{plan_id}/complete", response_model=TrainingPlanResponse)
def complete_training_plan(
    plan_id: int,
    company_id: int,
    actual_total_hours: float | None = None,
    actual_total_cost: float | None = None,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    plan = _plan_query(db, company_id).filter(
        TrainingPlan.plan_id == plan_id,
    ).first()

    if plan is None:
        raise HTTPException(
            status_code=404,
            detail="Training plan not found"
        )

    ensure_employee_access(context, db, plan.employee_id)
    if plan.plan_status != "Active":
        raise HTTPException(
            status_code=400,
            detail="Only active plans can be completed"
        )

    if actual_total_hours is not None and actual_total_hours < 0:
        raise HTTPException(
            status_code=422,
            detail="Actual hours cannot be negative"
        )

    if actual_total_cost is not None and actual_total_cost < 0:
        raise HTTPException(
            status_code=422,
            detail="Actual cost cannot be negative"
        )

    plan.plan_status = "Completed"
    actor = get_membership_employee(context, db, required=False)
    plan.status_updated_by = actor.id if actor else None
    plan.status_updated_by_user_id = context.user.user_id
    plan.actual_completion_date = date.today()
    plan.actual_total_hours = actual_total_hours
    plan.actual_total_cost = actual_total_cost

    db.commit()
    db.refresh(plan)

    return plan


# 8. RECORD PLAN REVIEW
@router.put("/{plan_id}/review", response_model=TrainingPlanResponse)
def review_training_plan(
    plan_id: int,
    company_id: int,
    review_data: TrainingPlanReview,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    plan = _plan_query(db, company_id).filter(
        TrainingPlan.plan_id == plan_id,
    ).first()

    if plan is None:
        raise HTTPException(
            status_code=404,
            detail="Training plan not found"
        )

    ensure_employee_access(context, db, plan.employee_id)
    plan.last_reviewed_at = datetime.utcnow()
    plan.plan_review_notes = review_data.plan_review_notes
    plan.reviewed_by_user_id = context.user.user_id

    db.commit()
    db.refresh(plan)

    return plan