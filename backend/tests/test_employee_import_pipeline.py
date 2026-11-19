from datetime import date
from io import BytesIO
import json
from pathlib import Path

import backend.app.db.models
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from openpyxl import Workbook
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.api.dependencies import authorize_business_request, get_db
from backend.app.api.employee_imports import router as employee_imports_router
from backend.app.core.security import create_access_token
from backend.app.db.auth_models import User, UserCompanyRole
from backend.app.db.base import Base
from backend.app.db.company import Company
from backend.app.db.employee import Employee
from backend.app.db.import_batch import ImportBatch
from backend.app.db.import_row_issue import ImportRowIssue
from backend.app.services.employee_import_pipeline import (
    build_employee_import_preview,
)
from backend.app.services.file_reader import (
    WorksheetSelectionRequired,
    read_tabular_file,
)
import backend.app.api.employee_imports as employee_imports_module


TABLE_NAMES = (
    "companies",
    "users",
    "revoked_access_tokens",
    "employees",
    "user_company_roles",
    "import_batches",
    "import_row_issues",
)


def _employee(
    employee_id: int,
    company_id: int,
    employee_code: str,
) -> Employee:
    return Employee(
        id=employee_id,
        company_id=company_id,
        employee_id=employee_code,
        full_name=f"Employee {employee_code}",
        email=f"{employee_code.lower()}@example.test",
        job_title="Engineer",
        department="Engineering",
        employment_status="Active",
        hire_date=date(2020, 1, 1),
        job_level="Individual Contributor",
        employment_type="Full-time",
        is_active=True,
    )


@pytest.fixture
def import_env(monkeypatch, tmp_path):
    monkeypatch.setenv("JWT_SECRET_KEY", "employee-import-test-secret-123456")
    monkeypatch.setattr(
        employee_imports_module,
        "IMPORT_STORAGE_ROOT",
        tmp_path / "imports",
    )

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    tables = [Base.metadata.tables[name] for name in TABLE_NAMES]
    Base.metadata.create_all(engine, tables=tables)
    test_session = sessionmaker(bind=engine, expire_on_commit=False)

    with test_session() as db:
        db.add_all([
            Company(company_id=1, company_name="Company One"),
            Company(company_id=2, company_name="Company Two"),
        ])
        db.add_all([
            _employee(10, 1, "TM"),
            _employee(20, 2, "FOREIGN"),
        ])
        db.add_all([
            User(
                user_id=1,
                full_name="Training Manager",
                email="tm@example.test",
                password_hash="not-used",
                is_active=True,
            ),
            User(
                user_id=2,
                full_name="Employee",
                email="employee@example.test",
                password_hash="not-used",
                is_active=True,
            ),
            User(
                user_id=3,
                full_name="Foreign Training Manager",
                email="foreign-tm@example.test",
                password_hash="not-used",
                is_active=True,
            ),
        ])
        db.add_all([
            UserCompanyRole(
                membership_id=1,
                user_id=1,
                company_id=1,
                employee_id=10,
                role="Training Manager",
                is_active=True,
            ),
            UserCompanyRole(
                membership_id=2,
                user_id=2,
                company_id=1,
                employee_id=None,
                role="Employee",
                is_active=True,
            ),
            UserCompanyRole(
                membership_id=3,
                user_id=3,
                company_id=2,
                employee_id=20,
                role="Training Manager",
                is_active=True,
            ),
            ImportBatch(
                id=40,
                company_id=2,
                created_by_user_id=3,
                source_type="CSV",
                entity_type="employee",
                file_name="foreign.csv",
                status="Completed",
                total_rows=1,
                successful_rows=1,
                failed_rows=0,
            ),
        ])
        db.commit()

    app = FastAPI()
    app.include_router(
        employee_imports_router,
        dependencies=[Depends(authorize_business_request)],
    )

    def override_get_db():
        with test_session() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db

    try:
        yield TestClient(app), test_session
    finally:
        Base.metadata.drop_all(engine, tables=list(reversed(tables)))
        engine.dispose()


def _headers(user_id: int, company_id: int = 1) -> dict[str, str]:
    token = create_access_token(user_id)
    return {
        "Authorization": f"Bearer {token}",
        "X-Company-ID": str(company_id),
    }


def _employee_record(
    employee_id: str,
    *,
    email: str | None = None,
    manager_id: str | None = None,
) -> dict[str, object]:
    return {
        "employee_id": employee_id,
        "full_name": f"Employee {employee_id}",
        "email": email or f"{employee_id.lower()}@example.test",
        "job_title": "Engineer",
        "department": "Engineering",
        "employment_status": "Active",
        "hire_date": "2024-01-15",
        "job_level": "Individual Contributor",
        "employment_type": "Full-time",
        "manager_id": manager_id,
    }


def test_csv_xlsx_xls_and_json_parsers(import_env):
    xlsx_book = Workbook()
    first_sheet = xlsx_book.active
    first_sheet.title = "Employees"
    first_sheet.append(["employee_id", "full_name"])
    first_sheet.append(["XLSX-1", "Excel Employee"])
    second_sheet = xlsx_book.create_sheet("Other")
    second_sheet.append(["employee_id", "full_name"])
    second_sheet.append(["XLSX-2", "Second Sheet"])
    xlsx_bytes = BytesIO()
    xlsx_book.save(xlsx_bytes)

    csv_result = read_tabular_file(
        b"employee_id,full_name\nCSV-1,CSV Employee\n",
        "employees.csv",
    )
    json_result = read_tabular_file(
        json.dumps([{"employee_id": "JSON-1", "full_name": "JSON Employee"}])
        .encode(),
        "employees.json",
    )
    xls_path = (
        Path(__file__).parent / "fixtures" / "employees_legacy.xls"
    )
    xls_result = read_tabular_file(xls_path.read_bytes(), "employees.xls")

    assert csv_result["rows"][0]["employee_id"] == "CSV-1"
    assert json_result["rows"][0]["employee_id"] == "JSON-1"
    assert xls_result["rows"][0]["employee_id"] == "XLS-001"

    with pytest.raises(WorksheetSelectionRequired) as selection:
        read_tabular_file(
            xlsx_bytes.getvalue(),
            "employees.xlsx",
            require_sheet_selection=True,
        )
    assert selection.value.sheet_names == ["Employees", "Other"]

    selected = read_tabular_file(
        xlsx_bytes.getvalue(),
        "employees.xlsx",
        sheet_name="Other",
        require_sheet_selection=True,
    )
    assert selected["worksheet"] == "Other"
    assert selected["rows"][0]["employee_id"] == "XLSX-2"


def test_rejects_duplicate_excel_headers(import_env):
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(["employee_id", "employee_id"])
    worksheet.append(["A1", "A2"])
    content = BytesIO()
    workbook.save(content)

    with pytest.raises(ValueError, match="duplicate"):
        read_tabular_file(content.getvalue(), "duplicate-headers.xlsx")


@pytest.mark.parametrize(
    ("content", "filename"),
    [
        (b"not,csv\n\"unterminated", "bad.csv"),
        (b"PK\x03\x04invalid", "bad.xlsx"),
        (b"{}", "bad.json"),
        (b"[{\"employee_id\":{\"nested\":true}}]", "bad.json"),
        (b"<employees/>", "bad.xml"),
    ],
)
def test_rejects_malformed_and_unsupported_files(import_env, content, filename):
    with pytest.raises(ValueError):
        read_tabular_file(content, filename)


def test_preview_reports_missing_duplicate_and_invalid_manager_records(import_env):
    _, test_session = import_env
    columns = [
        "employee_id",
        "full_name",
        "email",
        "job_title",
        "department",
        "employment_status",
        "hire_date",
        "job_level",
        "employment_type",
        "manager_id",
    ]
    mapping = {column: column for column in columns}

    with test_session() as db:
        rows = [
            _employee_record("DUPLICATE"),
            _employee_record("DUPLICATE", email="second@example.test"),
            _employee_record("Case-ID"),
            _employee_record("case-id", email="case-id-2@example.test"),
            _employee_record("CROSS-COMPANY", manager_id="FOREIGN"),
            _employee_record("UNKNOWN-MANAGER", manager_id="UNKNOWN"),
            _employee_record("TM"),
        ]
        preview = build_employee_import_preview(
            db, 1, columns, rows, mapping
        )
        errors = preview["errors"]
        duplicate_rows = {
            error["row_number"]
            for error in errors
            if error["type"] == "duplicate_in_file"
        }

        assert duplicate_rows == {2, 3, 4, 5}
        assert any(
            error["type"] == "invalid_manager_reference"
            and error["raw_value"] == "FOREIGN"
            for error in errors
        )
        assert any(
            error["type"] == "invalid_manager_reference"
            and error["raw_value"] == "UNKNOWN"
            for error in errors
        )
        assert any(
            error["type"] == "duplicate_in_database"
            and error["field"] == "employee_id"
            for error in errors
        )
        assert preview["summary"]["invalid_rows"] == 7

        missing_mapping = dict(mapping)
        missing_mapping.pop("department")
        incomplete = build_employee_import_preview(
            db, 1, columns, [_employee_record("MISSING-MAP")],
            missing_mapping,
        )
        assert "department" in incomplete["missing_mappings"]
        assert incomplete["summary"]["ready_for_confirmation"] is False

        reporting_cycle = build_employee_import_preview(
            db,
            1,
            columns,
            [
                _employee_record("CYCLE-A", manager_id="CYCLE-B"),
                _employee_record("CYCLE-B", manager_id="CYCLE-A"),
                _employee_record("SELF", manager_id="SELF"),
            ],
            mapping,
        )
        assert any(
            error["type"] == "manager_cycle"
            for error in reporting_cycle["errors"]
        )
        assert any(
            error["type"] == "invalid_manager_reference"
            and error["raw_value"] == "SELF"
            for error in reporting_cycle["errors"]
        )


def test_training_manager_preview_requires_confirmation_before_writes(import_env):
    client, test_session = import_env
    csv_content = (
        "employee_id,full_name,email,job_title,department,"
        "employment_status,hire_date,employment_type,manager_id,company_id\n"
        "NEW-MGR,New Manager,new-manager@example.test,Manager,Engineering,"
        "Active,2024-01-15,Full-time,TM,2\n"
        "NEW-EMP,New Employee,new-employee@example.test,Engineer,Engineering,"
        "Active,2024-01-15,Full-time,NEW-MGR,2\n"
    ).encode()
    headers = _headers(1)

    with test_session() as db:
        starting_company_one = db.query(Employee).filter(
            Employee.company_id == 1
        ).count()
        starting_company_two = db.query(Employee).filter(
            Employee.company_id == 2
        ).count()

    upload = client.post(
        "/employee-imports/upload",
        headers=headers,
        files={"file": ("employees.csv", csv_content, "text/csv")},
    )
    assert upload.status_code == 200
    batch_id = upload.json()["batch_id"]

    preview = client.post(
        f"/employee-imports/{batch_id}/preview",
        headers=headers,
        json={},
    )
    assert preview.status_code == 200
    assert preview.json()["summary"]["importable_rows"] == 2
    assert preview.json()["column_mapping"]["company_id"] is None

    with test_session() as db:
        assert db.query(Employee).filter(
            Employee.company_id == 1
        ).count() == starting_company_one
        assert db.query(Employee).filter(
            Employee.company_id == 2
        ).count() == starting_company_two

    declined = client.post(
        f"/employee-imports/{batch_id}/confirm",
        headers=headers,
        json={"confirmed": False},
    )
    assert declined.status_code == 400

    confirmed = client.post(
        f"/employee-imports/{batch_id}/confirm",
        headers=headers,
        json={"confirmed": True},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["summary"]["successful_rows"] == 2

    with test_session() as db:
        imported = db.query(Employee).filter(
            Employee.company_id == 1,
            Employee.employee_id.in_(["NEW-MGR", "NEW-EMP"]),
        ).all()
        assert len(imported) == 2
        imported_by_code = {
            employee.employee_id: employee for employee in imported
        }
        assert imported_by_code["NEW-MGR"].manager_internal_id == 10
        assert (
            imported_by_code["NEW-EMP"].manager_internal_id
            == imported_by_code["NEW-MGR"].id
        )
        warning_issues = db.query(ImportRowIssue).filter(
            ImportRowIssue.batch_id == batch_id
        ).all()
        assert len(warning_issues) == 2
        assert all(issue.status == "Resolved" for issue in warning_issues)
        assert db.query(Employee).filter(
            Employee.company_id == 2
        ).count() == starting_company_two


def test_preview_records_row_errors_without_importing_employees(import_env):
    client, test_session = import_env
    csv_content = (
        "employee_id,full_name,email,job_title,department,"
        "employment_status,hire_date,employment_type\n"
        "TM,Duplicate Employee,duplicate@example.test,Engineer,Engineering,"
        "Active,2024-01-15,Full-time\n"
    ).encode()
    headers = _headers(1)

    with test_session() as db:
        starting_count = db.query(Employee).filter(
            Employee.company_id == 1
        ).count()

    upload = client.post(
        "/employee-imports/upload",
        headers=headers,
        files={"file": ("duplicate.csv", csv_content, "text/csv")},
    )
    assert upload.status_code == 200
    batch_id = upload.json()["batch_id"]
    preview = client.post(
        f"/employee-imports/{batch_id}/preview",
        headers=headers,
        json={},
    )
    assert preview.status_code == 200
    assert preview.json()["summary"]["invalid_rows"] == 1

    with test_session() as db:
        assert db.query(Employee).filter(
            Employee.company_id == 1
        ).count() == starting_count
        issues = db.query(ImportRowIssue).filter(
            ImportRowIssue.batch_id == batch_id
        ).all()
        assert any(
            issue.issue_type == "duplicate_in_database"
            and issue.status == "Open"
            for issue in issues
        )
        assert any(
            issue.issue_type.startswith("warning_")
            and issue.status == "Resolved"
            for issue in issues
        )

    issues_response = client.get(
        f"/employee-imports/{batch_id}/issues?company_id=1&status=Open",
        headers=headers,
    )
    assert issues_response.status_code == 200
    assert issues_response.json()["total_issues"] == 1


def test_import_authorization_and_company_isolation(import_env):
    client, _ = import_env

    unauthenticated = client.get("/employee-imports/history")
    assert unauthenticated.status_code == 401

    employee_upload = client.post(
        "/employee-imports/upload",
        headers=_headers(2),
        files={
            "file": (
                "employees.json",
                b'[{"employee_id":"E1"}]',
                "application/json",
            )
        },
    )
    assert employee_upload.status_code == 403

    company_tamper = client.get(
        "/employee-imports/history?company_id=2",
        headers=_headers(1),
    )
    assert company_tamper.status_code in {400, 403}

    foreign_batch = client.post(
        "/employee-imports/40/preview?company_id=1",
        headers=_headers(1),
        json={},
    )
    assert foreign_batch.status_code == 404

    company_one_history = client.get(
        "/employee-imports/history",
        headers=_headers(1),
    )
    assert company_one_history.status_code == 200
    assert 40 not in {
        batch["batch_id"]
        for batch in company_one_history.json()["batches"]
    }
