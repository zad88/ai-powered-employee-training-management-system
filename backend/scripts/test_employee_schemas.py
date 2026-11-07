
from datetime import date
from decimal import Decimal

from pydantic import ValidationError

from backend.app.schemas.employee import (
    EmployeeCreate,
    EmployeeUpdate,
)


employee_data = {
    "employee_id": "EMP001",
    "full_name": "Ahmed Mohamed",
    "email": "ahmed@example.com",
    "job_title": "AI Engineer",
    "department": "Technology",
    "manager_id": None,
    "employment_status": "Active",
    "working_hours_per_week": Decimal("40"),
    "learning_hours_per_week": Decimal("5"),
    "years_of_experience": Decimal("2.5"),
    "hire_date": date(2024, 1, 15),
    "job_level": "Junior",
    "employment_type": "Full-time",
    "preferred_learning_mode": "Online",
}


# Test 1: Valid employee
employee = EmployeeCreate(**employee_data)
print("Valid employee:", employee.full_name)


# Test 2: Invalid email
try:
    EmployeeCreate(**{
        **employee_data,
        "email": "not-an-email"
    })
except ValidationError:
    print("Invalid email correctly rejected")


# Test 3: Negative working hours
try:
    EmployeeCreate(**{
        **employee_data,
        "working_hours_per_week": -10
    })
except ValidationError:
    print("Negative working hours correctly rejected")


# Test 4: Partial update
update = EmployeeUpdate(job_title="Senior AI Engineer")
print("Partial update:", update.model_dump(exclude_unset=True))
