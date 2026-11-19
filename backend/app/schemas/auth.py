from pydantic import BaseModel, ConfigDict, EmailStr


class MembershipResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    membership_id: int
    company_id: int
    employee_id: int | None
    role: str
    is_active: bool


class UserResponse(BaseModel):
    user_id: int
    full_name: str
    email: EmailStr
    is_active: bool
    memberships: list[MembershipResponse]


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
