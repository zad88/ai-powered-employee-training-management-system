from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SessionAttendanceCreate(BaseModel):
    session_id: int = Field(gt=0)
    employee_id: int = Field(gt=0)

    attendance_status: str = Field(
        default="Pending",
        pattern="^(Pending|Present|Absent|Late|Excused)$"
    )

    attendance_notes: str | None = None


class SessionAttendanceUpdate(BaseModel):
    attendance_status: str | None = Field(
        default=None,
        pattern="^(Pending|Present|Absent|Late|Excused)$"
    )

    attendance_notes: str | None = None


class SessionAttendanceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    attendance_id: int
    company_id: int
    session_id: int
    employee_id: int

    attendance_status: str

    check_in_time: datetime | None = None
    check_out_time: datetime | None = None

    recorded_by: int | None = None
    attendance_notes: str | None = None