# AI-Powered Employee Training Management System

## Authentication configuration

Copy `.env.example` to `.env` for the backend and replace the database
credentials and `JWT_SECRET_KEY` with deployment-specific values. The JWT
secret must contain at least 32 characters and must not be committed.

Configure `FRONTEND_ORIGINS` as a comma-separated list of trusted browser
origins for backend cookie-authenticated requests. Configure `FRONTEND_ORIGIN`
and `BACKEND_URL` in the frontend environment (for example,
`frontend/.env.local`). In production, use HTTPS and set `NODE_ENV=production`;
the authentication cookies will then use the Secure attribute. The backend
rejects cookie-authenticated mutations in production if `FRONTEND_ORIGINS` is
not configured.

## Database and manager-link setup

After backing up the production database, review the pending Alembic migration
and apply it during a controlled deployment with
`python -m alembic upgrade head`. The pending migrations add nullable user
audit references and access-token revocation storage; they do not reset
existing business data.

Manager relationships are company-local and use `manager_internal_id`. Run
`python -m backend.scripts.reconcile_manager_links` to preview existing link
reconciliation; add `--apply` only after reviewing the dry-run output and
backing up the database.

## Access-token revocation

Logout revokes only the current JWT by its `jti`; tokens without a valid `jti`
are rejected and users must sign in again. Revocation records are retained only
until their token expiry. Schedule
`python -m backend.scripts.cleanup_expired_token_revocations` to run daily so
expired records are removed without affecting active sessions.

## Employee imports

Training Managers can upload CSV, Excel (`.xlsx` or `.xls`), and JSON files
from the Employee Imports page. Uploads are limited to 20 MiB and 10,000 data
rows. When an Excel workbook has multiple worksheets, select the worksheet
containing employee records.

JSON input must be a non-empty array of flat employee objects. For example:

```json
[
  {
    "employee_id": "EMP-001",
    "full_name": "Example Employee",
    "email": "employee@example.com",
    "job_title": "Analyst",
    "department": "Operations",
    "employment_status": "Active",
    "hire_date": "2024-01-15",
    "job_level": "Individual Contributor",
    "employment_type": "Full-time"
  }
]
```

The upload workflow stages each file, suggests mappings, and previews row-level
validation before requiring explicit confirmation. Supported mappings include
employee ID, name, email, department, job title, manager ID/name, employment
status/type, hire date, job level, working and learning hours, years of
experience, and preferred learning mode. A `company_id` in a file is not
imported; the active authenticated company membership determines ownership.
Invalid rows are not silently discarded: their errors and warnings are shown
in the preview and retained with the import history.

## Odoo employee import integration

The Employee Imports page can use Odoo as a read-only additional source.
Configure these environment variables in the backend `.env` file:

```dotenv
ODOO_BASE_URL=http://localhost:8069
ODOO_DATABASE=odoo_training_test
ODOO_USERNAME=integration@example.com
ODOO_API_KEY=generate-this-in-odoo
ODOO_API_TIMEOUT=30
```

Create a dedicated Odoo integration user, grant read access only to
`hr.employee`, `hr.department`, `hr.job`, and `res.company`, and generate an
API key under the Odoo user's Preferences / Account Security / New API Key.
Never commit the API key. The backend returns configuration status and
diagnostics only; it does not return or display the key.

The connector supports Odoo 17 and 18 through the documented XML-RPC API,
Odoo 19 and 20 through JSON-2 when available, and XML-RPC fallback where
authenticated legacy RPC remains available. Odoo 19 JSON-2 requires bearer API
key authentication and may be unavailable on editions or plans that do not
expose the external API. Version detection is read-only.

The Odoo data is fetched in pages, normalized through the existing employee
column mapping and validation pipeline, and staged as a normal company-scoped
`ODOO` import batch. Preview does not write Employee records. Explicit
confirmation is still required. Odoo source database and record IDs are retained
as batch metadata; employees are not overwritten automatically.

For the supplied local test environment, no Docker data or containers need to
change. Keep `odoo_test`, `odoo_test_db`, `training_db`, and their volumes
untouched. Odoo 19 is available at `http://localhost:8069`; the test database
is `odoo_training_test`. Start or stop only your application processes, not
the existing database containers.

Common PowerShell commands:

```powershell
cd C:\Users\ZAD MAHMOUD\Downloads\ai-powered-employee-training-management-system
Copy-Item .env.example .env -ErrorAction SilentlyContinue
# Edit .env, then start the existing application
uvicorn backend.app.main:app --reload
cd frontend
npm.cmd run dev
```

Test with mocked APIs using:

```powershell
& .\.venv\Scripts\python.exe -m pytest backend/tests/test_odoo_integration.py -q
```