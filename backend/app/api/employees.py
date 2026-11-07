
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_db
from backend.app.db.employee import Employee
from backend.app.schemas.employee import (
    EmployeeCreate,
    EmployeeUpdate,
    EmployeeResponse
)


router = APIRouter(
    prefix="/employees",
    tags=["Employees"]
)


# 1. CREATE EMPLOYEE
@router.post("/", response_model=EmployeeResponse, status_code=201)
def create_employee(
    employee_data: EmployeeCreate,
    company_id: int,
    db: Session = Depends(get_db)
):
    existing_employee = db.query(Employee).filter(
        Employee.company_id == company_id,
        Employee.employee_id == employee_data.employee_id
    ).first()

    if existing_employee:
        raise HTTPException(
            status_code=409,
            detail="Employee ID already exists in this company"
        )

    existing_email = db.query(Employee).filter(
        Employee.company_id == company_id,
        Employee.email == str(employee_data.email)
    ).first()

    if existing_email:
        raise HTTPException(
            status_code=409,
            detail="Email already exists in this company"
        )

    new_employee = Employee(
        **employee_data.model_dump(),
        company_id=company_id
    )

    db.add(new_employee)
    db.commit()
    db.refresh(new_employee)

    return new_employee


# 2. GET ALL ACTIVE EMPLOYEES
@router.get("/", response_model=list[EmployeeResponse])
def get_employees(
    company_id: int,
    db: Session = Depends(get_db)
):
    employees = db.query(Employee).filter(
        Employee.company_id == company_id,
        Employee.is_active == True
    ).all()

    return employees


# 3. GET ONE ACTIVE EMPLOYEE BY DATABASE ID
@router.get("/{employee_id}", response_model=EmployeeResponse)
def get_employee(
    employee_id: int,
    company_id: int,
    db: Session = Depends(get_db)
):
    employee = db.query(Employee).filter(
        Employee.id == employee_id,
        Employee.company_id == company_id,
        Employee.is_active == True
    ).first()

    if employee is None:
        raise HTTPException(
            status_code=404,
            detail="Active employee not found in this company"
        )

    return employee


# 4. UPDATE EMPLOYEE
@router.put("/{employee_id}", response_model=EmployeeResponse)
def update_employee(
    employee_id: int,
    employee_data: EmployeeUpdate,
    company_id: int,
    db: Session = Depends(get_db)
):
    employee = db.query(Employee).filter(
        Employee.id == employee_id,
        Employee.company_id == company_id,
        Employee.is_active == True
    ).first()

    if employee is None:
        raise HTTPException(
            status_code=404,
            detail="Active employee not found in this company"
        )

    update_data = employee_data.model_dump(exclude_unset=True)

    if "email" in update_data and update_data["email"] is not None:
        existing_email = db.query(Employee).filter(
            Employee.company_id == company_id,
            Employee.email == str(update_data["email"]),
            Employee.id != employee_id
        ).first()

        if existing_email:
            raise HTTPException(
                status_code=409,
                detail="Email already exists in this company"
            )

    for field, value in update_data.items():
        setattr(employee, field, value)

    db.commit()
    db.refresh(employee)

    return employee


# 5. SOFT DELETE EMPLOYEE
@router.delete("/{employee_id}")
def delete_employee(
    employee_id: int,
    company_id: int,
    db: Session = Depends(get_db)
):
    employee = db.query(Employee).filter(
        Employee.id == employee_id,
        Employee.company_id == company_id,
        Employee.is_active == True
    ).first()

    if employee is None:
        raise HTTPException(
            status_code=404,
            detail="Active employee not found in this company"
        )

    employee.is_active = False

    db.commit()

    return {
        "message": "Employee deactivated successfully",
        "employee_id": employee.employee_id
    }
