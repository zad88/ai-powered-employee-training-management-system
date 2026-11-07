from pydantic import BaseModel, ConfigDict, Field


class SkillCreate(BaseModel):
    skill_name: str = Field(min_length=2, max_length=150)
    description: str | None = None
    category: str | None = Field(default=None, max_length=100)


class SkillUpdate(BaseModel):
    skill_name: str | None = Field(default=None, min_length=2, max_length=150)
    description: str | None = None
    category: str | None = Field(default=None, max_length=100)


class SkillResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    skill_id: int
    skill_name: str
    description: str | None = None
    category: str | None = None