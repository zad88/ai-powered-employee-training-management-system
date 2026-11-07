from pydantic import BaseModel, ConfigDict, Field


class PlanCourseCreate(BaseModel):
    plan_id: int = Field(gt=0)
    course_id: int = Field(gt=0)

    priority: str = Field(
        default="Medium",
        pattern="^(Low|Medium|High)$"
    )

    sequence_order: int = Field(ge=1)

    recommendation_reason: str | None = None
    expected_outcome: str | None = None


class PlanCourseUpdate(BaseModel):
    priority: str | None = Field(
        default=None,
        pattern="^(Low|Medium|High)$"
    )

    sequence_order: int | None = Field(default=None, ge=1)

    recommendation_reason: str | None = None
    expected_outcome: str | None = None


class PlanCourseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    plan_course_id: int
    plan_id: int
    course_id: int

    priority: str
    sequence_order: int

    recommendation_reason: str | None = None
    expected_outcome: str | None = None