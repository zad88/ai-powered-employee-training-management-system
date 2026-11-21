from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.api.dependencies import AuthContext, get_db, require_roles
from backend.app.db.company import Company
from backend.app.db.company_esco_occupation_mapping import (
    CompanyESCOOccupationMapping,
)
from backend.app.db.employee import Employee
from backend.app.db.esco_occupation import ESCOOccupation
from backend.app.db.esco_occupation_skill import ESCOOccupationSkill
from backend.app.db.job_skill import JobSkill


router = APIRouter(prefix="/company-esco-mappings", tags=["ESCO Job Mapping"])
training_manager = require_roles("Training Manager")


class MappingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_title: str = Field(min_length=1, max_length=150)
    occupation_id: int = Field(gt=0)


class ReviewedSkill(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skill_id: int = Field(gt=0)
    required_proficiency: int = Field(ge=1, le=5)
    importance: Literal["Low", "Medium", "High", "Critical"]


class ConfirmRequest(MappingRequest):
    skills: list[ReviewedSkill] = Field(min_length=1)


def _company_title(db: Session, company_id: int, title: str) -> str:
    result = (
        db.query(Employee.job_title)
        .filter(
            Employee.company_id == company_id,
            func.lower(func.trim(Employee.job_title)) == title.strip().lower(),
        )
        .order_by(Employee.job_title)
        .first()
    )
    if result is None or not title.strip():
        raise HTTPException(404, "Job title not found in your company.")
    return result[0].strip()


def _mapping(db: Session, company_id: int, title: str):
    return (
        db.query(CompanyESCOOccupationMapping)
        .filter(
            CompanyESCOOccupationMapping.company_id == company_id,
            func.lower(func.trim(CompanyESCOOccupationMapping.job_title))
            == title.lower(),
        )
        .first()
    )


def _lock_company(db: Session, company_id: int) -> None:
    db.query(Company.company_id).filter(
        Company.company_id == company_id
    ).with_for_update().one()


@router.get("/titles")
def company_job_titles(
    context: AuthContext = Depends(training_manager),
    db: Session = Depends(get_db),
):
    rows = db.query(Employee.job_title).filter(
        Employee.company_id == context.company_id
    ).order_by(Employee.job_title).all()
    titles: dict[str, str] = {}
    for (title,) in rows:
        clean = title.strip()
        if clean:
            titles.setdefault(clean.lower(), clean)
    return list(titles.values())


@router.get("/mapping")
def get_mapping(
    job_title: str = Query(min_length=1, max_length=150),
    context: AuthContext = Depends(training_manager),
    db: Session = Depends(get_db),
):
    title = _company_title(db, context.company_id, job_title)
    mapping = _mapping(db, context.company_id, title)
    return {
        "job_title": title,
        "occupation_id": mapping.occupation_id if mapping else None,
    }


@router.put("/mapping")
def save_mapping(
    request: MappingRequest,
    context: AuthContext = Depends(training_manager),
    db: Session = Depends(get_db),
):
    _lock_company(db, context.company_id)
    title = _company_title(db, context.company_id, request.job_title)
    if db.get(ESCOOccupation, request.occupation_id) is None:
        raise HTTPException(404, "ESCO occupation not found.")
    mapping = _mapping(db, context.company_id, title)
    if mapping is None:
        mapping = CompanyESCOOccupationMapping(
            company_id=context.company_id,
            job_title=title,
            occupation_id=request.occupation_id,
        )
        db.add(mapping)
    else:
        mapping.occupation_id = request.occupation_id
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Mapping changed concurrently. Please retry.") from exc
    return {"job_title": title, "occupation_id": request.occupation_id}


@router.post("/requirements", status_code=201)
def confirm_requirements(
    request: ConfirmRequest,
    context: AuthContext = Depends(training_manager),
    db: Session = Depends(get_db),
):
    _lock_company(db, context.company_id)
    title = _company_title(db, context.company_id, request.job_title)
    mapping = _mapping(db, context.company_id, title)
    if mapping is None or mapping.occupation_id != request.occupation_id:
        raise HTTPException(409, "Save the occupation mapping before confirming.")
    ids = [item.skill_id for item in request.skills]
    if len(ids) != len(set(ids)):
        raise HTTPException(422, "Each selected skill must appear only once.")
    valid_ids = {
        row[0] for row in db.query(ESCOOccupationSkill.skill_id).filter(
            ESCOOccupationSkill.occupation_id == mapping.occupation_id,
            ESCOOccupationSkill.skill_id.in_(ids),
        ).all()
    }
    if valid_ids != set(ids):
        raise HTTPException(422, "Selected skills must belong to the mapped occupation.")
    existing_ids = {
        row[0] for row in db.query(JobSkill.skill_id).filter(
            JobSkill.company_id == context.company_id,
            func.lower(func.trim(JobSkill.job_title)) == title.lower(),
            JobSkill.skill_id.in_(ids),
        ).all()
    }
    for item in request.skills:
        if item.skill_id not in existing_ids:
            db.add(JobSkill(
                company_id=context.company_id,
                job_title=title,
                skill_id=item.skill_id,
                required_proficiency=item.required_proficiency,
                importance=item.importance,
                approval_status="Pending",
            ))
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            409, "Requirements changed concurrently. Please review and retry."
        ) from exc
    return {
        "created": len(ids) - len(existing_ids),
        "already_existing": len(existing_ids),
    }
