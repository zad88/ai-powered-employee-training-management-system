from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from backend.app.api.dependencies import get_db
from backend.app.db.esco_occupation import ESCOOccupation
from backend.app.db.esco_occupation_skill import ESCOOccupationSkill


router = APIRouter(
    prefix="/esco-occupations",
    tags=["ESCO Occupations"],
)


def _occupation_summary(occupation: ESCOOccupation) -> dict:
    return {
        "id": occupation.id,
        "esco_concept_uri": occupation.esco_concept_uri,
        "preferred_label": occupation.preferred_label,
        "alternative_labels": occupation.alternative_labels,
        "description": occupation.description,
        "isco_group": occupation.isco_group,
        "code": occupation.code,
    }


@router.get("/")
def get_esco_occupations(
    search: str | None = Query(default=None, min_length=1, max_length=200),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query = db.query(ESCOOccupation)

    if search:
        search_term = f"%{search.strip()}%"
        query = query.filter(
            ESCOOccupation.preferred_label.ilike(search_term)
            | ESCOOccupation.alternative_labels.ilike(search_term)
        )

    total = query.count()

    occupations = (
        query
        .order_by(ESCOOccupation.preferred_label.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return {
        "items": [
            _occupation_summary(occupation)
            for occupation in occupations
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
    }


@router.get("/{occupation_id}")
def get_esco_occupation(
    occupation_id: int,
    db: Session = Depends(get_db),
):
    occupation = (
        db.query(ESCOOccupation)
        .options(
            joinedload(ESCOOccupation.skill_relations)
            .joinedload(ESCOOccupationSkill.skill)
        )
        .filter(ESCOOccupation.id == occupation_id)
        .first()
    )

    if occupation is None:
        raise HTTPException(
            status_code=404,
            detail="ESCO occupation not found",
        )

    skills = []

    for relation in occupation.skill_relations:
        skill = relation.skill

        skills.append({
            "skill_id": skill.skill_id,
            "skill_name": skill.skill_name,
            "esco_concept_uri": skill.esco_concept_uri,
            "description": skill.description,
            "alternative_labels": skill.alternative_labels,
            "skill_type": relation.skill_type or skill.esco_skill_type,
            "relation_type": relation.relation_type,
        })

    skills.sort(
        key=lambda item: (
            item["relation_type"] != "essential",
            (item["skill_name"] or "").casefold(),
        )
    )

    result = _occupation_summary(occupation)
    result.update({
        "definition": occupation.definition,
        "scope_note": occupation.scope_note,
        "regulated_profession_note": occupation.regulated_profession_note,
        "nace_code": occupation.nace_code,
        "status": occupation.status,
        "modified_date": occupation.modified_date,
        "skills": skills,
        "essential_skills_count": sum(
            skill["relation_type"] == "essential"
            for skill in skills
        ),
        "optional_skills_count": sum(
            skill["relation_type"] == "optional"
            for skill in skills
        ),
    })

    return result
