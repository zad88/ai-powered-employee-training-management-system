from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from backend.app.api.dependencies import get_db
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
    db: Session = Depends(get_db)
):
    query = db.query(JobSkill).filter(
        JobSkill.company_id == company_id
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
    db: Session = Depends(get_db)
):
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

    db.commit()
    db.refresh(requirement)

    return requirement


# 5. APPROVE OR REJECT JOB REQUIREMENT
@router.put("/{requirement_id}/approval", response_model=JobSkillResponse)
def approve_job_skill(
    requirement_id: int,
    company_id: int,
    approval_data: JobSkillApproval,
    approved_by: int,
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

    manager = db.query(Employee).filter(
        Employee.id == approved_by,
        Employee.company_id == company_id,
        Employee.is_active == True
    ).first()

    if manager is None:
        raise HTTPException(
            status_code=404,
            detail="Approving employee not found in this company"
        )

    requirement.approval_status = approval_data.approval_status
    requirement.approved_by = manager.id

    db.commit()
    db.refresh(requirement)

    return requirement