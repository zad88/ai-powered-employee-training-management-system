from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CourseSessionCreate(BaseModel):
    course_id: int = Field(gt=0)

    session_name: str | None = Field(default=None, max_length=150)

    start_datetime: datetime
    end_datetime: datetime
    registration_deadline: datetime

    trainer_name: str | None = Field(default=None, max_length=150)

    location_type: str = Field(min_length=1, max_length=30)
    location_details: str | None = None

    max_participants: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_dates(self):
        if self.end_datetime <= self.start_datetime:
            raise ValueError("End time must be after start time")

        if self.registration_deadline > self.start_datetime:
            raise ValueError("Registration deadline cannot be after session start")

        return self


class CourseSessionUpdate(BaseModel):
    session_name: str | None = Field(default=None, max_length=150)

    start_datetime: datetime | None = None
    end_datetime: datetime | None = None
    registration_deadline: datetime | None = None

    trainer_name: str | None = Field(default=None, max_length=150)

    location_type: str | None = Field(default=None, max_length=30)
    location_details: str | None = None

    max_participants: int | None = Field(default=None, gt=0)


class CourseSessionStatusUpdate(BaseModel):
    session_status: str = Field(
        pattern="^(Scheduled|In Progress|Completed|Cancelled)$"
    )


class CourseSessionCompletion(BaseModel):
    completion_status: str = Field(
        pattern="^(Completed|Partially Completed|Not Completed)$"
    )
    completion_date: datetime
    completion_notes: str | None = None


class CourseSessionCancellation(BaseModel):
    cancellation_reason: str = Field(min_length=1)


class CourseSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    session_id: int
    company_id: int
    course_id: int

    session_name: str | None = None

    start_datetime: datetime
    end_datetime: datetime
    registration_deadline: datetime

    session_status: str

    trainer_name: str | None = None
    location_type: str
    location_details: str | None = None

    max_participants: int | None = None

    completion_status: str | None = None
    completion_date: datetime | None = None
    completion_notes: str | None = None

    cancellation_reason: str | None = None
    cancelled_at: datetime | None = None
    cancelled_by: int | None = None