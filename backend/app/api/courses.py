from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_db
from backend.app.db.course import Course
from backend.app.schemas.course import (
    CourseCreate,
    CourseUpdate,
    CourseStatusUpdate,
    CourseResponse
)


router = APIRouter(
    prefix="/courses",
    tags=["Courses"]
)


# 1. CREATE COURSE
@router.post("/", response_model=CourseResponse, status_code=201)
def create_course(
    course_data: CourseCreate,
    company_id: int,
    db: Session = Depends(get_db)
):
    existing_course = db.query(Course).filter(
        Course.company_id == company_id,
        Course.course_id == course_data.course_id
    ).first()

    if existing_course:
        raise HTTPException(
            status_code=409,
            detail="Course ID already exists in this company"
        )

    new_course = Course(
        **course_data.model_dump(),
        company_id=company_id,
        is_active=True
    )

    db.add(new_course)
    db.commit()
    db.refresh(new_course)

    return new_course


# 2. GET ALL COURSES
@router.get("/", response_model=list[CourseResponse])
def get_courses(
    company_id: int,
    active_only: bool = True,
    db: Session = Depends(get_db)
):
    query = db.query(Course).filter(
        Course.company_id == company_id
    )

    if active_only:
        query = query.filter(Course.is_active == True)

    return query.order_by(Course.course_title).all()


# 3. GET ONE COURSE
@router.get("/{course_db_id}", response_model=CourseResponse)
def get_course(
    course_db_id: int,
    company_id: int,
    db: Session = Depends(get_db)
):
    course = db.query(Course).filter(
        Course.id == course_db_id,
        Course.company_id == company_id
    ).first()

    if course is None:
        raise HTTPException(
            status_code=404,
            detail="Course not found"
        )

    return course


# 4. UPDATE COURSE
@router.put("/{course_db_id}", response_model=CourseResponse)
def update_course(
    course_db_id: int,
    company_id: int,
    course_data: CourseUpdate,
    db: Session = Depends(get_db)
):
    course = db.query(Course).filter(
        Course.id == course_db_id,
        Course.company_id == company_id
    ).first()

    if course is None:
        raise HTTPException(
            status_code=404,
            detail="Course not found"
        )

    update_data = course_data.model_dump(exclude_unset=True)

    new_start = update_data.get("start_date", course.start_date)
    new_end = update_data.get("end_date", course.end_date)

    if (
        new_start is not None
        and new_end is not None
        and new_end < new_start
    ):
        raise HTTPException(
            status_code=422,
            detail="End date cannot be before start date"
        )

    for field, value in update_data.items():
        setattr(course, field, value)

    db.commit()
    db.refresh(course)

    return course


# 5. ACTIVATE OR DEACTIVATE COURSE
@router.patch("/{course_db_id}/status", response_model=CourseResponse)
def update_course_status(
    course_db_id: int,
    company_id: int,
    status_data: CourseStatusUpdate,
    db: Session = Depends(get_db)
):
    course = db.query(Course).filter(
        Course.id == course_db_id,
        Course.company_id == company_id
    ).first()

    if course is None:
        raise HTTPException(
            status_code=404,
            detail="Course not found"
        )

    course.is_active = status_data.is_active

    db.commit()
    db.refresh(course)

    return course