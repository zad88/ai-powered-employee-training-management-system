from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.db.auth_models import User, UserCompanyRole
from backend.app.db.employee import Employee


def validate_reporting_manager(
    db: Session, company_id: int, manager_id: int, employee_id: int | None,
) -> Employee:
    manager = db.query(Employee).join(
        UserCompanyRole, UserCompanyRole.employee_id == Employee.id
    ).join(User, User.user_id == UserCompanyRole.user_id).filter(
        Employee.id == manager_id, Employee.company_id == company_id,
        Employee.is_active.is_(True), UserCompanyRole.company_id == company_id,
        UserCompanyRole.is_active.is_(True), User.is_active.is_(True),
        func.lower(func.trim(UserCompanyRole.role)).in_(["manager", "training manager", "director"]),
    ).first()
    if manager is None:
        raise HTTPException(422, "Select an active company manager.")
    visited = {employee_id} if employee_id is not None else set()
    cursor = manager
    while cursor is not None:
        if cursor.id in visited:
            raise HTTPException(422, "The reporting relationship would create a cycle.")
        visited.add(cursor.id)
        if cursor.manager_internal_id is None:
            break
        cursor = db.query(Employee).filter(
            Employee.id == cursor.manager_internal_id, Employee.company_id == company_id,
        ).first()
        if cursor is None:
            raise HTTPException(422, "The manager hierarchy contains an invalid company link.")
    return manager
