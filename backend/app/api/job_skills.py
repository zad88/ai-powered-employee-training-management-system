from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.api.dependencies import (
    AuthContext,
    allowed_employee_ids,
    get_auth_context,
    get_db,
    get_membership_employee,
)
from backend.app.db.job_skill import JobSkill
from backend.app.db.skill import Skill
from backend.app.db.employee import Employee
from backend.app.schemas.job_skill import (
    JobSkillCreate,
    JobSkillUpdate,
    JobSkillApproval,
    JobSkillResponse
)


router = APIRouter(
    prefix="/job-skills",
    tags=["Job Requirements"]
)


def _visible_job_titles(
    context: AuthContext,
    company_id: int,
    db: Session,
) -> set[str] | None:
    employee_ids = allowed_employee_ids(context, db)
    if employee_ids is None:
        return None
    return {
        row[0].strip().casefold()
        for row in db.query(Employee.job_title).filter(
            Employee.company_id == company_id,
            Employee.id.in_(employee_ids),
        ).all()
    }


# 1. CREATE JOB REQUIREMENT
@router.post("/", response_model=JobSkillResponse, status_code=201)
def create_job_skill(
    requirement_data: JobSkillCreate,
    company_id: int,
    db: Session = Depends(get_db)
):
    skill = db.query(Skill).filter(
        Skill.skill_id == requirement_data.skill_id
    ).first()

    if skill is None:
        raise HTTPException(
            status_code=404,
            detail="Skill not found"
        )

    existing_requirement = db.query(JobSkill).filter(
        JobSkill.company_id == company_id,
        JobSkill.job_title.ilike(requirement_data.job_title),
        JobSkill.skill_id == requirement_data.skill_id
    ).first()

    if existing_requirement:
        raise HTTPException(
            status_code=409,
            detail="This skill is already assigned to this job title"
        )

    new_requirement = JobSkill(
        **requirement_data.model_dump(),
        company_id=company_id,
        approval_status="Pending"
    )

    db.add(new_requirement)
    db.commit()
    db.refresh(new_requirement)

    return new_requirement


# 2. GET ALL JOB REQUIREMENTS
@router.get("/", response_model=list[JobSkillResponse])
def get_job_skills(
    company_id: int,
    job_title: str | None = None,
    approval_status: str | None = None,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    query = db.query(JobSkill).filter(
        JobSkill.company_id == company_id
    )
    visible_titles = _visible_job_titles(context, company_id, db)
    if visible_titles is not None:
        if job_title and job_title.strip().casefold() not in visible_titles:
            return []
        query = query.filter(
            func.lower(JobSkill.job_title).in_(visible_titles)
        )

    if job_title:
        query = query.filter(
            JobSkill.job_title.ilike(job_title)
        )

    if approval_status:
        query = query.filter(
            JobSkill.approval_status == approval_status
        )

    return query.order_by(JobSkill.job_title).all()


# 3. GET REQUIREMENTS FOR ONE JOB
@router.get("/by-job/{job_title}", response_model=list[JobSkillResponse])
def get_requirements_by_job(
    job_title: str,
    company_id: int,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    visible_titles = _visible_job_titles(context, company_id, db)
    if (
        visible_titles is not None
        and job_title.strip().casefold() not in visible_titles
    ):
        return []
    requirements = db.query(JobSkill).filter(
        JobSkill.company_id == company_id,
        JobSkill.job_title.ilike(job_title)
    ).all()

    return requirements


# 4. UPDATE JOB REQUIREMENT
@router.put("/{requirement_id}", response_model=JobSkillResponse)
def update_job_skill(
    requirement_id: int,
    company_id: int,
    requirement_data: JobSkillUpdate,
    db: Session = Depends(get_db)
):
    requirement = db.query(JobSkill).filter(
        JobSkill.id == requirement_id,
        JobSkill.company_id == company_id
    ).first()

    if requirement is None:
        raise HTTPException(
            status_code=404,
            detail="Job requirement not found"
        )

    update_data = requirement_data.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(requirement, field, value)

    # Changes require approval again
    if update_data:
        requirement.approval_status = "Pending"
        requirement.approved_by = None
        requirement.approved_by_user_id = None

    db.commit()
    db.refresh(requirement)

    return requirement


# 5. APPROVE OR REJECT JOB REQUIREMENT
@router.put("/{requirement_id}/approval", response_model=JobSkillResponse)
def approve_job_skill(
    requirement_id: int,
    company_id: int,
    approval_data: JobSkillApproval,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    requirement = db.query(JobSkill).filter(
        JobSkill.id == requirement_id,
        JobSkill.company_id == company_id
    ).first()

    if requirement is None:
        raise HTTPException(
            status_code=404,
            detail="Job requirement not found"
        )

    requirement.approval_status = approval_data.approval_status
    approver = get_membership_employee(context, db, required=False)
    requirement.approved_by = approver.id if approver else None
    requirement.approved_by_user_id = context.user.user_id

    db.commit()
    db.refresh(requirement)

    return requirement