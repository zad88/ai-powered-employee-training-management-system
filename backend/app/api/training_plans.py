from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_db

from backend.app.db.employee import Employee
from backend.app.db.training_plan import TrainingPlan

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


# 1. CREATE TRAINING PLAN
@router.post("/", response_model=TrainingPlanResponse, status_code=201)
def create_training_plan(
    company_id: int,
    created_by: int,
    plan_data: TrainingPlanCreate,
    db: Session = Depends(get_db)
):
    employee = db.query(Employee).filter(
        Employee.id == plan_data.employee_id,
        Employee.company_id == company_id,
        Employee.is_active == True
    ).first()

    if employee is None:
        raise HTTPException(
            status_code=404,
            detail="Employee not found in this company"
        )

    creator = db.query(Employee).filter(
        Employee.id == created_by,
        Employee.company_id == company_id,
        Employee.is_active == True
    ).first()

    if creator is None:
        raise HTTPException(
            status_code=404,
            detail="Plan creator not found in this company"
        )

    new_plan = TrainingPlan(
        **plan_data.model_dump(),
        company_id=company_id,
        created_by=created_by,
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
    db: Session = Depends(get_db)
):
    query = db.query(TrainingPlan).filter(
        TrainingPlan.company_id == company_id
    )

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
    db: Session = Depends(get_db)
):
    plan = db.query(TrainingPlan).filter(
        TrainingPlan.plan_id == plan_id,
        TrainingPlan.company_id == company_id
    ).first()

    if plan is None:
        raise HTTPException(
            status_code=404,
            detail="Training plan not found"
        )

    return plan


# 4. UPDATE DRAFT TRAINING PLAN
@router.put("/{plan_id}", response_model=TrainingPlanResponse)
def update_training_plan(
    plan_id: int,
    company_id: int,
    plan_data: TrainingPlanUpdate,
    db: Session = Depends(get_db)
):
    plan = db.query(TrainingPlan).filter(
        TrainingPlan.plan_id == plan_id,
        TrainingPlan.company_id == company_id
    ).first()

    if plan is None:
        raise HTTPException(
            status_code=404,
            detail="Training plan not found"
        )

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
    approved_by: int,
    approval_data: TrainingPlanApproval,
    db: Session = Depends(get_db)
):
    plan = db.query(TrainingPlan).filter(
        TrainingPlan.plan_id == plan_id,
        TrainingPlan.company_id == company_id
    ).first()

    if plan is None:
        raise HTTPException(
            status_code=404,
            detail="Training plan not found"
        )

    if plan.plan_status != "Draft":
        raise HTTPException(
            status_code=400,
            detail="Only draft plans can be approved or rejected"
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

    if approval_data.approval_status == "Approved":
        plan.plan_status = "Approved"
    else:
        plan.plan_status = "Draft"

    plan.approval_status = approval_data.approval_status
    plan.approved_by = approved_by
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
    db: Session = Depends(get_db)
):
    plan = db.query(TrainingPlan).filter(
        TrainingPlan.plan_id == plan_id,
        TrainingPlan.company_id == company_id
    ).first()

    if plan is None:
        raise HTTPException(
            status_code=404,
            detail="Training plan not found"
        )

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
    db: Session = Depends(get_db)
):
    plan = db.query(TrainingPlan).filter(
        TrainingPlan.plan_id == plan_id,
        TrainingPlan.company_id == company_id
    ).first()

    if plan is None:
        raise HTTPException(
            status_code=404,
            detail="Training plan not found"
        )

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
    db: Session = Depends(get_db)
):
    plan = db.query(TrainingPlan).filter(
        TrainingPlan.plan_id == plan_id,
        TrainingPlan.company_id == company_id
    ).first()

    if plan is None:
        raise HTTPException(
            status_code=404,
            detail="Training plan not found"
        )

    plan.last_reviewed_at = datetime.utcnow()
    plan.plan_review_notes = review_data.plan_review_notes

    db.commit()
    db.refresh(plan)

    return plan