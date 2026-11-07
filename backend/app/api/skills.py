from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_db
from backend.app.db.skill import Skill
from backend.app.schemas.skill import (
    SkillCreate,
    SkillUpdate,
    SkillResponse
)


router = APIRouter(
    prefix="/skills",
    tags=["Skills"]
)


# 1. CREATE SKILL
@router.post("/", response_model=SkillResponse, status_code=201)
def create_skill(
    skill_data: SkillCreate,
    db: Session = Depends(get_db)
):
    existing_skill = db.query(Skill).filter(
        Skill.skill_name.ilike(skill_data.skill_name)
    ).first()

    if existing_skill:
        raise HTTPException(
            status_code=409,
            detail="Skill already exists"
        )

    new_skill = Skill(
        **skill_data.model_dump()
    )

    db.add(new_skill)
    db.commit()
    db.refresh(new_skill)

    return new_skill


# 2. GET ALL SKILLS
@router.get("/", response_model=list[SkillResponse])
def get_skills(
    db: Session = Depends(get_db)
):
    return db.query(Skill).order_by(Skill.skill_name).all()


# 3. GET ONE SKILL
@router.get("/{skill_id}", response_model=SkillResponse)
def get_skill(
    skill_id: int,
    db: Session = Depends(get_db)
):
    skill = db.query(Skill).filter(
        Skill.skill_id == skill_id
    ).first()

    if skill is None:
        raise HTTPException(
            status_code=404,
            detail="Skill not found"
        )

    return skill


# 4. UPDATE SKILL
@router.put("/{skill_id}", response_model=SkillResponse)
def update_skill(
    skill_id: int,
    skill_data: SkillUpdate,
    db: Session = Depends(get_db)
):
    skill = db.query(Skill).filter(
        Skill.skill_id == skill_id
    ).first()

    if skill is None:
        raise HTTPException(
            status_code=404,
            detail="Skill not found"
        )

    update_data = skill_data.model_dump(exclude_unset=True)

    if "skill_name" in update_data and update_data["skill_name"] is not None:
        existing_skill = db.query(Skill).filter(
            Skill.skill_name.ilike(update_data["skill_name"]),
            Skill.skill_id != skill_id
        ).first()

        if existing_skill:
            raise HTTPException(
                status_code=409,
                detail="Skill name already exists"
            )

    for field, value in update_data.items():
        setattr(skill, field, value)

    db.commit()
    db.refresh(skill)

    return skill