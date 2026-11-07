from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class EnrollmentAssessmentCreate(BaseModel):
    enrollment_id: int = Field(gt=0)
    attempt_number: int = Field(ge=1)

    assessment_score: float | None = Field(
        default=None,
        ge=0,
        le=100
    )

    assessment_result: str = Field(
        min_length=1,
        max_length=30
    )

    assessor_comments: str | None = None


class EnrollmentAssessmentUpdate(BaseModel):
    assessment_score: float | None = Field(
        default=None,
        ge=0,
        le=100
    )

    assessment_result: str | None = Field(
        default=None,
        min_length=1,
        max_length=30
    )

    assessor_comments: str | None = None


class EnrollmentAssessmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    assessment_id: int
    company_id: int
    enrollment_id: int

    attempt_number: int
    assessment_score: float | None = None
    assessment_result: str

    assessed_at: datetime
    assessor_comments: str | None = None