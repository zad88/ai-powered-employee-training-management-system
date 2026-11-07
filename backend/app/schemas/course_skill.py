from pydantic import BaseModel, ConfigDict, Field


class CourseSkillCreate(BaseModel):
    course_id: int = Field(gt=0)
    skill_id: int = Field(gt=0)
    proficiency_level: int | None = Field(default=None, ge=1, le=5)


class CourseSkillApproval(BaseModel):
    approval_status: str = Field(pattern="^(Approved|Rejected)$")


class CourseSkillResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    course_id: int
    skill_id: int
    proficiency_level: int | None = None
    approval_status: str
    approved_by: int | None = None