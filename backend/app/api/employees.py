
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.api.dependencies import (
    AuthContext,
    allowed_employee_ids,
    ensure_employee_access,
    get_auth_context,
    get_db,
)
from backend.app.db.employee import Employee
from backend.app.db.company import Company
from backend.app.services.employee_reporting import validate_reporting_manager
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
    manager_internal_id = None
    if employee_data.manager_id:
        db.query(Company.company_id).filter(
            Company.company_id == company_id
        ).with_for_update().one()
        manager = db.query(Employee).filter(
            Employee.company_id == company_id,
            Employee.employee_id == employee_data.manager_id,
            Employee.is_active.is_(True),
        ).first()
        if manager is None:
            raise HTTPException(
                status_code=422,
                detail="Manager must be an active employee in this company.",
            )
        validate_reporting_manager(db, company_id, manager.id, None)
        manager_internal_id = manager.id

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
        company_id=company_id,
        manager_internal_id=manager_internal_id,
    )

    db.add(new_employee)
    db.commit()
    db.refresh(new_employee)

    return new_employee


# 2. GET ALL ACTIVE EMPLOYEES
@router.get("/", response_model=list[EmployeeResponse])
def get_employees(
    company_id: int,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    query = db.query(Employee).filter(
        Employee.company_id == company_id,
        Employee.is_active.is_(True),
    )
    employee_ids = allowed_employee_ids(context, db)
    if employee_ids is not None:
        query = query.filter(Employee.id.in_(employee_ids))

    return query.order_by(Employee.id).all()


# 3. GET ONE ACTIVE EMPLOYEE BY DATABASE ID
@router.get("/{employee_id}", response_model=EmployeeResponse)
def get_employee(
    employee_id: int,
    company_id: int,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    return ensure_employee_access(context, db, employee_id)


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

    if "manager_id" in update_data:
        manager_id = update_data["manager_id"]
        manager = None
        db.query(Company.company_id).filter(
            Company.company_id == company_id
        ).with_for_update().one()
        if manager_id:
            manager = db.query(Employee).filter(
                Employee.company_id == company_id,
                Employee.employee_id == manager_id,
                Employee.is_active.is_(True),
                Employee.id != employee_id,
            ).first()
            if manager is None:
                raise HTTPException(
                    status_code=422,
                    detail="Manager must be another active employee in this company.",
                )
            validate_reporting_manager(db, company_id, manager.id, employee.id)
        employee.manager_internal_id = manager.id if manager else None
        employee.manager_id = manager.employee_id if manager else None

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
        if field == "manager_id":
            continue
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
