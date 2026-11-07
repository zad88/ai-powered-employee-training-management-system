from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SessionFeedbackCreate(BaseModel):
    session_id: int = Field(gt=0)

    training_rating: int = Field(ge=1, le=5)
    trainer_rating: int | None = Field(default=None, ge=1, le=5)
    content_relevance_rating: int | None = Field(default=None, ge=1, le=5)

    feedback_comments: str | None = None


class SessionFeedbackUpdate(BaseModel):
    training_rating: int | None = Field(default=None, ge=1, le=5)
    trainer_rating: int | None = Field(default=None, ge=1, le=5)
    content_relevance_rating: int | None = Field(default=None, ge=1, le=5)

    feedback_comments: str | None = None


class SessionFeedbackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    feedback_id: int
    company_id: int
    session_id: int
    employee_id: int

    training_rating: int
    trainer_rating: int | None = None
    content_relevance_rating: int | None = None

    feedback_comments: str | None = None
    submitted_at: datetime