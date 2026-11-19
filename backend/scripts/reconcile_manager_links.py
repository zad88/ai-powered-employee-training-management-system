import argparse

from sqlalchemy.orm import Session

from backend.app.db.database import SessionLocal
from backend.app.db.employee import Employee


def reconcile_company_manager_links(
    db: Session,
    company_id: int,
) -> tuple[int, int]:
    employees = db.query(Employee).filter(
        Employee.company_id == company_id,
    ).all()
    employee_by_code = {
        employee.employee_id.strip().casefold(): employee
        for employee in employees
    }
    employee_by_id = {employee.id: employee for employee in employees}

    updated = 0
    unresolved = 0
    for employee in employees:
        expected_manager_id = None
        manager_code = (employee.manager_id or "").strip().casefold()
        if manager_code:
            manager = employee_by_code.get(manager_code)
            if (
                manager is not None
                and manager.is_active
                and manager.id != employee.id
            ):
                expected_manager_id = manager.id
            else:
                unresolved += 1
        elif employee.manager_internal_id is not None:
            linked_manager = employee_by_id.get(employee.manager_internal_id)
            if linked_manager is None or not linked_manager.is_active:
                expected_manager_id = None
            else:
                expected_manager_id = linked_manager.id

        if employee.manager_internal_id != expected_manager_id:
            employee.manager_internal_id = expected_manager_id
            updated += 1

    return updated, unresolved


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reconcile manager_internal_id from company-local employee IDs."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist changes. Without this flag the command is a dry run.",
    )
    args = parser.parse_args()

    db: Session = SessionLocal()
    try:
        company_ids = [
            row[0]
            for row in db.query(Employee.company_id).distinct().all()
        ]
        total_updated = 0
        total_unresolved = 0
        for company_id in company_ids:
            updated, unresolved = reconcile_company_manager_links(
                db,
                company_id,
            )
            total_updated += updated
            total_unresolved += unresolved

        if args.apply:
            db.commit()
        else:
            db.rollback()

        action = "Applied" if args.apply else "Dry run"
        print(
            f"{action}: {total_updated} manager links would be updated; "
            f"{total_unresolved} references remain unresolved."
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
