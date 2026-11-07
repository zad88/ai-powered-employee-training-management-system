from datetime import date

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SkillAssessmentCreate(BaseModel):
    employee_id: int = Field(gt=0)
    skill_id: int = Field(gt=0)

    proficiency_level: int = Field(ge=1, le=5)

    assessment_source: str = Field(min_length=1, max_length=50)
    assessment_score: float | None = Field(default=None, ge=0, le=100)

    evidence_quality: str = Field(
        default="Medium",
        pattern="^(Low|Medium|High)$"
    )

    assessment_date: date
    expiry_date: date | None = None

    assessor_comments: str | None = None

    @model_validator(mode="after")
    def validate_dates(self):
        if (
            self.expiry_date is not None
            and self.expiry_date < self.assessment_date
        ):
            raise ValueError("Expiry date cannot be before assessment date")

        return self


class SkillAssessmentUpdate(BaseModel):
    proficiency_level: int | None = Field(default=None, ge=1, le=5)

    assessment_source: str | None = Field(default=None, max_length=50)
    assessment_score: float | None = Field(default=None, ge=0, le=100)

    evidence_quality: str | None = Field(
        default=None,
        pattern="^(Low|Medium|High)$"
    )

    assessment_date: date | None = None
    expiry_date: date | None = None

    assessor_comments: str | None = None


class SkillAssessmentReview(BaseModel):
    evidence_status: str = Field(
        pattern="^(Approved|Rejected|Pending Review)$"
    )


class SkillAssessmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    assessment_id: int
    company_id: int
    employee_id: int
    skill_id: int

    proficiency_level: int

    assessment_source: str
    assessment_score: float | None = None

    evidence_quality: str
    assessment_date: date
    expiry_date: date | None = None

    assessor_comments: str | None = None
    evidence_status: str