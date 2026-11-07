from pydantic import BaseModel, ConfigDict, Field


class JobSkillCreate(BaseModel):
    job_title: str = Field(min_length=2, max_length=150)
    skill_id: int = Field(gt=0)
    required_proficiency: int = Field(ge=1, le=5)
    importance: str = Field(default="Medium", max_length=30)


class JobSkillUpdate(BaseModel):
    required_proficiency: int | None = Field(default=None, ge=1, le=5)
    importance: str | None = Field(default=None, max_length=30)


class JobSkillApproval(BaseModel):
    approval_status: str = Field(pattern="^(Approved|Rejected)$")


class JobSkillResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    job_title: str
    skill_id: int
    required_proficiency: int
    importance: str
    approval_status: str
    approved_by: int | None = None