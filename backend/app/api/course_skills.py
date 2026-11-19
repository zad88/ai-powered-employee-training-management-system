from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.api.dependencies import (
    AuthContext,
    get_auth_context,
    get_db,
    get_membership_employee,
)
from backend.app.db.course import Course
from backend.app.db.course_skill import CourseSkill
from backend.app.db.skill import Skill
from backend.app.schemas.course_skill import (
    CourseSkillCreate,
    CourseSkillApproval,
    CourseSkillResponse
)


router = APIRouter(
    prefix="/course-skills",
    tags=["Course Skills"]
)


# 1. CONNECT COURSE TO SKILL
@router.post("/", response_model=CourseSkillResponse, status_code=201)
def create_course_skill(
    company_id: int,
    association_data: CourseSkillCreate,
    db: Session = Depends(get_db)
):
    course = db.query(Course).filter(
        Course.id == association_data.course_id,
        Course.company_id == company_id
    ).first()

    if course is None:
        raise HTTPException(
            status_code=404,
            detail="Course not found in this company"
        )

    skill = db.query(Skill).filter(
        Skill.skill_id == association_data.skill_id
    ).first()

    if skill is None:
        raise HTTPException(
            status_code=404,
            detail="Skill not found"
        )

    existing = db.query(CourseSkill).filter(
        CourseSkill.company_id == company_id,
        CourseSkill.course_id == association_data.course_id,
        CourseSkill.skill_id == association_data.skill_id
    ).first()

    if existing:
        raise HTTPException(
            status_code=409,
            detail="This course is already connected to this skill"
        )

    new_association = CourseSkill(
        **association_data.model_dump(),
        company_id=company_id,
        approval_status="Pending"
    )

    db.add(new_association)
    db.commit()
    db.refresh(new_association)

    return new_association


# 2. GET COURSE-SKILL ASSOCIATIONS
@router.get("/", response_model=list[CourseSkillResponse])
def get_course_skills(
    company_id: int,
    course_id: int | None = None,
    approval_status: str | None = None,
    db: Session = Depends(get_db)
):
    query = db.query(CourseSkill).join(
        Course,
        CourseSkill.course_id == Course.id,
    ).filter(
        CourseSkill.company_id == company_id,
        Course.company_id == company_id,
    )

    if course_id is not None:
        query = query.filter(
            CourseSkill.course_id == course_id
        )

    if approval_status is not None:
        query = query.filter(
            CourseSkill.approval_status == approval_status
        )

    return query.all()


# 3. APPROVE OR REJECT COURSE-SKILL ASSOCIATION
@router.put("/{association_id}/approval", response_model=CourseSkillResponse)
def approve_course_skill(
    association_id: int,
    company_id: int,
    approval_data: CourseSkillApproval,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    association = db.query(CourseSkill).join(
        Course,
        CourseSkill.course_id == Course.id,
    ).filter(
        CourseSkill.id == association_id,
        CourseSkill.company_id == company_id,
        Course.company_id == company_id,
    ).first()

    if association is None:
        raise HTTPException(
            status_code=404,
            detail="Course-skill association not found"
        )

    association.approval_status = approval_data.approval_status
    approver = get_membership_employee(context, db, required=False)
    association.approved_by = approver.id if approver else None
    association.approved_by_user_id = context.user.user_id

    db.commit()
    db.refresh(association)

    return association