from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


AssessmentSource = Literal[
    "Manager Assessment",
    "Technical Test",
    "Practical Demonstration",
    "Self-Assessment",
    "Project or Work Sample",
    "Certificate",
    "Peer Assessment",
    "External Assessment",
]

EvidenceQuality = Literal["Low", "Medium", "High"]

EvidenceStatus = Literal[
    "Approved",
    "Rejected",
    "Pending Review",
]


class SkillAssessmentCreate(BaseModel):
    employee_id: int = Field(gt=0)
    skill_id: int = Field(gt=0)

    proficiency_level: int = Field(ge=1, le=5)

    assessment_source: AssessmentSource
    assessment_score: float | None = Field(
        default=None,
        ge=0,
        le=100
    )

    evidence_quality: EvidenceQuality = "Medium"

    evidence_title: str = Field(
        min_length=2,
        max_length=200
    )

    evidence_description: str | None = Field(
        default=None,
        max_length=5000
    )

    assessment_date: date
    expiry_date: date | None = None

    assessor_comments: str | None = Field(
        default=None,
        max_length=5000
    )

    @model_validator(mode="after")
    def validate_dates(self):
        if (
            self.expiry_date is not None
            and self.expiry_date < self.assessment_date
        ):
            raise ValueError(
                "Expiry date cannot be before assessment date"
            )

        return self


class SkillAssessmentUpdate(BaseModel):
    proficiency_level: int | None = Field(
        default=None,
        ge=1,
        le=5
    )

    assessment_source: AssessmentSource | None = None

    assessment_score: float | None = Field(
        default=None,
        ge=0,
        le=100
    )

    evidence_quality: EvidenceQuality | None = None

    evidence_title: str | None = Field(
        default=None,
        min_length=2,
        max_length=200
    )

    evidence_description: str | None = Field(
        default=None,
        max_length=5000
    )

    assessment_date: date | None = None
    expiry_date: date | None = None

    assessor_comments: str | None = Field(
        default=None,
        max_length=5000
    )


class SkillAssessmentReview(BaseModel):
    evidence_status: EvidenceStatus


class SkillAssessmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    assessment_id: int
    company_id: int
    employee_id: int
    skill_id: int
    assessed_by: int | None = None
    assessed_by_user_id: int | None = None
    reviewed_by: int | None = None
    reviewed_by_user_id: int | None = None

    proficiency_level: int

    assessment_source: str
    assessment_score: float | None = None

    evidence_quality: str

    evidence_title: str | None = None
    evidence_description: str | None = None

    assessment_date: date
    expiry_date: date | None = None

    assessor_comments: str | None = None
    evidence_status: str
