
from datetime import date

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CourseCreate(BaseModel):
    course_id: str = Field(min_length=1, max_length=100)
    course_title: str = Field(min_length=2, max_length=200)
    course_description: str | None = None
    course_category: str = Field(min_length=1, max_length=100)

    course_duration_hours: float = Field(gt=0)

    course_provider: str | None = Field(default=None, max_length=150)
    delivery_mode: str = Field(min_length=1, max_length=30)

    start_date: date | None = None
    end_date: date | None = None

    target_job_levels: str | None = Field(default=None, max_length=300)
    prerequisites: str | None = None

    has_assessment: bool = False
    provides_certificate: bool = False
    assessment_type: str = Field(default="None", max_length=50)

    course_cost: float | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, max_length=10)

    @model_validator(mode="after")
    def validate_dates(self):
        if (
            self.start_date is not None
            and self.end_date is not None
            and self.end_date < self.start_date
        ):
            raise ValueError("End date cannot be before start date")

        return self


class CourseUpdate(BaseModel):
    course_title: str | None = Field(default=None, min_length=2, max_length=200)
    course_description: str | None = None
    course_category: str | None = Field(default=None, max_length=100)

    course_duration_hours: float | None = Field(default=None, gt=0)

    course_provider: str | None = Field(default=None, max_length=150)
    delivery_mode: str | None = Field(default=None, max_length=30)

    start_date: date | None = None
    end_date: date | None = None

    target_job_levels: str | None = Field(default=None, max_length=300)
    prerequisites: str | None = None

    has_assessment: bool | None = None
    provides_certificate: bool | None = None
    assessment_type: str | None = Field(default=None, max_length=50)

    course_cost: float | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, max_length=10)

    @model_validator(mode="after")
    def validate_dates(self):
        if (
            self.start_date is not None
            and self.end_date is not None
            and self.end_date < self.start_date
        ):
            raise ValueError("End date cannot be before start date")

        return self


class CourseStatusUpdate(BaseModel):
    is_active: bool


class CourseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    course_id: str
    course_title: str
    course_description: str | None = None
    course_category: str
    course_duration_hours: float
    course_provider: str | None = None
    delivery_mode: str
    is_active: bool
    start_date: date | None = None
    end_date: date | None = None
    target_job_levels: str | None = None
    prerequisites: str | None = None
    has_assessment: bool
    provides_certificate: bool
    assessment_type: str
    course_cost: float | None = None
    currency: str | None = None
