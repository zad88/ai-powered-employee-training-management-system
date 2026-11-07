from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_db

from backend.app.db.training_plan import TrainingPlan
from backend.app.db.course import Course
from backend.app.db.plan_course import PlanCourse

from backend.app.schemas.plan_course import (
    PlanCourseCreate,
    PlanCourseUpdate,
    PlanCourseResponse,
)


router = APIRouter(
    prefix="/plan-courses",
    tags=["Plan Courses"]
)


# 1. ADD COURSE TO TRAINING PLAN
@router.post("/", response_model=PlanCourseResponse, status_code=201)
def add_course_to_plan(
    company_id: int,
    course_data: PlanCourseCreate,
    db: Session = Depends(get_db)
):
    plan = db.query(TrainingPlan).filter(
        TrainingPlan.plan_id == course_data.plan_id,
        TrainingPlan.company_id == company_id
    ).first()

    if plan is None:
        raise HTTPException(
            status_code=404,
            detail="Training plan not found"
        )

    if plan.plan_status != "Draft" or plan.approval_status != "Pending":
        raise HTTPException(
            status_code=400,
            detail="Courses can only be added to draft, pending plans"
        )

    course = db.query(Course).filter(
        Course.id == course_data.course_id,
        Course.company_id == company_id,
        Course.is_active == True
    ).first()

    if course is None:
        raise HTTPException(
            status_code=404,
            detail="Active course not found in this company"
        )

    existing = db.query(PlanCourse).filter(
        PlanCourse.plan_id == course_data.plan_id,
        PlanCourse.course_id == course_data.course_id
    ).first()

    if existing:
        raise HTTPException(
            status_code=409,
            detail="This course is already included in the plan"
        )

    existing_sequence = db.query(PlanCourse).filter(
        PlanCourse.plan_id == course_data.plan_id,
        PlanCourse.sequence_order == course_data.sequence_order
    ).first()

    if existing_sequence:
        raise HTTPException(
            status_code=409,
            detail="This sequence order is already used in the plan"
        )

    new_plan_course = PlanCourse(**course_data.model_dump())

    db.add(new_plan_course)
    db.commit()
    db.refresh(new_plan_course)

    return new_plan_course


# 2. GET COURSES IN A TRAINING PLAN
@router.get("/", response_model=list[PlanCourseResponse])
def get_plan_courses(
    company_id: int,
    plan_id: int,
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

    return db.query(PlanCourse).filter(
        PlanCourse.plan_id == plan_id
    ).order_by(
        PlanCourse.sequence_order
    ).all()


# 3. GET ONE PLAN COURSE
@router.get("/{plan_course_id}", response_model=PlanCourseResponse)
def get_plan_course(
    plan_course_id: int,
    company_id: int,
    db: Session = Depends(get_db)
):
    item = db.query(PlanCourse).join(
        TrainingPlan,
        PlanCourse.plan_id == TrainingPlan.plan_id
    ).filter(
        PlanCourse.plan_course_id == plan_course_id,
        TrainingPlan.company_id == company_id
    ).first()

    if item is None:
        raise HTTPException(
            status_code=404,
            detail="Plan course not found"
        )

    return item


# 4. UPDATE PLAN COURSE
@router.put("/{plan_course_id}", response_model=PlanCourseResponse)
def update_plan_course(
    plan_course_id: int,
    company_id: int,
    course_data: PlanCourseUpdate,
    db: Session = Depends(get_db)
):
    item = db.query(PlanCourse).join(
        TrainingPlan,
        PlanCourse.plan_id == TrainingPlan.plan_id
    ).filter(
        PlanCourse.plan_course_id == plan_course_id,
        TrainingPlan.company_id == company_id
    ).first()

    if item is None:
        raise HTTPException(
            status_code=404,
            detail="Plan course not found"
        )

    plan = item.training_plan

    if plan.plan_status != "Draft" or plan.approval_status != "Pending":
        raise HTTPException(
            status_code=400,
            detail="Only courses in draft, pending plans can be edited"
        )

    update_data = course_data.model_dump(exclude_unset=True)

    if "sequence_order" in update_data:
        duplicate_order = db.query(PlanCourse).filter(
            PlanCourse.plan_id == item.plan_id,
            PlanCourse.sequence_order == update_data["sequence_order"],
            PlanCourse.plan_course_id != plan_course_id
        ).first()

        if duplicate_order:
            raise HTTPException(
                status_code=409,
                detail="This sequence order is already used in the plan"
            )

    for field, value in update_data.items():
        setattr(item, field, value)

    db.commit()
    db.refresh(item)

    return item


# 5. REMOVE COURSE FROM TRAINING PLAN
@router.delete("/{plan_course_id}")
def remove_plan_course(
    plan_course_id: int,
    company_id: int,
    db: Session = Depends(get_db)
):
    item = db.query(PlanCourse).join(
        TrainingPlan,
        PlanCourse.plan_id == TrainingPlan.plan_id
    ).filter(
        PlanCourse.plan_course_id == plan_course_id,
        TrainingPlan.company_id == company_id
    ).first()

    if item is None:
        raise HTTPException(
            status_code=404,
            detail="Plan course not found"
        )

    if (
        item.training_plan.plan_status != "Draft"
        or item.training_plan.approval_status != "Pending"
    ):
        raise HTTPException(
            status_code=400,
            detail="Only courses in draft, pending plans can be removed"
        )

    db.delete(item)
    db.commit()

    return {"message": "Course removed from training plan successfully"}