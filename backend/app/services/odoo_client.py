import json
import os
import xmlrpc.client
from dataclasses import dataclass
from typing import Any, Iterable
from urllib.parse import urlparse

import requests


SUPPORTED_MAJOR_VERSIONS = {17, 18, 19, 20}


class OdooError(Exception):
    pass


class OdooConfigurationError(OdooError):
    pass


class OdooAuthenticationError(OdooError):
    pass


class OdooPermissionError(OdooError):
    pass


class OdooUnavailableError(OdooError):
    pass


class OdooFetchError(OdooError):
    pass


@dataclass(frozen=True)
class OdooConfig:
    base_url: str
    database: str
    username: str
    api_key: str
    timeout: float

    @classmethod
    def from_env(cls) -> "OdooConfig":
        base_url = os.getenv("ODOO_BASE_URL", "").strip().rstrip("/")
        database = os.getenv("ODOO_DATABASE", "").strip()
        username = os.getenv("ODOO_USERNAME", "").strip()
        api_key = os.getenv("ODOO_API_KEY", "").strip()
        try:
            timeout = float(os.getenv("ODOO_API_TIMEOUT", "30"))
        except ValueError as exc:
            raise OdooConfigurationError(
                "ODOO_API_TIMEOUT must be a number."
            ) from exc
        if timeout <= 0 or timeout > 300:
            raise OdooConfigurationError(
                "ODOO_API_TIMEOUT must be between 1 and 300 seconds."
            )

        missing = []
        if not base_url:
            missing.append("ODOO_BASE_URL")
        if not database:
            missing.append("ODOO_DATABASE")
        if not username:
            missing.append("ODOO_USERNAME")
        if not api_key:
            missing.append("ODOO_API_KEY")
        if missing:
            raise OdooConfigurationError(
                f"Missing Odoo configuration: {', '.join(missing)}."
            )

        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise OdooConfigurationError(
                "ODOO_BASE_URL must be a valid HTTP or HTTPS URL."
            )
        if parsed.scheme == "http" and not parsed.hostname in {
            "localhost",
            "127.0.0.1",
            "::1",
        }:
            raise OdooConfigurationError(
                "Production Odoo connections must use HTTPS."
            )
        return cls(
            base_url=base_url,
            database=database,
            username=username,
            api_key=api_key,
            timeout=timeout,
        )

    def safe_status(self) -> dict[str, Any]:
        return {
            "configured": True,
            "base_url": self.base_url,
            "database": self.database,
            "api_key_configured": bool(self.api_key),
        }


def _safe_http_error(response: requests.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        message = payload.get("message") or payload.get("error")
        if isinstance(message, dict):
            message = message.get("data") or message.get("message")
        if isinstance(message, str) and message:
            return message[:500]
    text = response.text.strip()
    if text:
        return text[:500]
    return f"Odoo returned HTTP {response.status_code}."


def detect_odoo_version(config: OdooConfig) -> dict[str, Any]:
    try:
        response = requests.post(
            f"{config.base_url}/web/webclient/version_info",
            json={},
            timeout=config.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        result = payload.get("result", payload)
        server_version = str(
            result.get("server_version")
            or result.get("server_serie")
            or ""
        )
        info = result.get("server_version_info")
        major = int(info[0]) if isinstance(info, list) and info else 0
        if not major:
            series = str(result.get("server_serie") or "").split(".")
            major = int(series[0]) if series and series[0].isdigit() else 0
        if not server_version and not major:
            raise OdooUnavailableError(
                "Odoo did not return recognizable version information."
            )
        return {
            "server_version": server_version,
            "major": major,
            "server_serie": str(result.get("server_serie") or server_version),
        }
    except requests.RequestException as exc:
        raise OdooUnavailableError(
            f"Could not reach Odoo: {type(exc).__name__}"
        ) from exc
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise OdooUnavailableError(
            "Odoo version endpoint returned an invalid response."
        ) from exc


def _relation_name(value: Any) -> str | None:
    if isinstance(value, list) and len(value) >= 2:
        return str(value[1]).strip() or None
    if isinstance(value, dict):
        name = value.get("display_name") or value.get("name")
        return str(name).strip() if name else None
    return None


class OdooAdapter:
    name = "provider-independent"

    def test_connection(self) -> dict[str, Any]:
        raise NotImplementedError

    def fields_get(self, model: str) -> dict[str, dict[str, Any]]:
        raise NotImplementedError

    def search_read(
        self,
        model: str,
        domain: list[Any],
        fields: list[str],
        *,
        offset: int = 0,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError

    def search_count(self, model: str, domain: list[Any]) -> int:
        raise NotImplementedError


class OdooJson2Adapter(OdooAdapter):
    name = "JSON-2"

    def __init__(self, config: OdooConfig):
        self.config = config

    def _call(
        self,
        model: str,
        method: str,
        body: dict[str, Any] | None = None,
    ) -> Any:
        try:
            response = requests.post(
                f"{self.config.base_url}/json/2/{model}/{method}",
                headers={
                    "Authorization": f"bearer {self.config.api_key}",
                    "Content-Type": "application/json",
                    "X-Odoo-Database": self.config.database,
                    "User-Agent": "AI-Employee-Training-Management",
                },
                json=body or {},
                timeout=self.config.timeout,
            )
        except requests.Timeout as exc:
            raise OdooUnavailableError(
                "Odoo API timed out."
            ) from exc
        except requests.RequestException as exc:
            raise OdooUnavailableError(
                f"Could not reach Odoo: {type(exc).__name__}"
            ) from exc

        if response.status_code in {401, 403}:
            raise OdooAuthenticationError(
                "Odoo rejected the API key or the integration account."
            )
        if response.status_code == 404:
            raise OdooUnavailableError(
                "The Odoo JSON-2 API route is unavailable."
            )
        if response.status_code == 429:
            raise OdooUnavailableError(
                "Odoo rate-limited the integration request."
            )
        if response.status_code >= 400:
            raise OdooFetchError(_safe_http_error(response))
        try:
            return response.json()
        except ValueError as exc:
            raise OdooFetchError(
                "Odoo JSON-2 returned an invalid JSON response."
            ) from exc

    def test_connection(self) -> dict[str, Any]:
        count = self.search_count("hr.employee", [])
        fields = self.fields_get("hr.employee")
        return {
            "employee_model_access": "available",
            "employee_count": count,
            "available_employee_fields": sorted(fields),
        }

    def fields_get(self, model: str) -> dict[str, dict[str, Any]]:
        response = self._call(
            model,
            "fields_get",
            {"attributes": ["string", "help", "type", "relation"]},
        )
        if not isinstance(response, dict):
            raise OdooPermissionError(
                f"Field discovery returned no field metadata for {model}."
            )
        return response

    def search_count(self, model: str, domain: list[Any]) -> int:
        response = self._call(model, "search_count", {"domain": domain})
        if not isinstance(response, int):
            raise OdooFetchError(
                f"Odoo returned an invalid count for {model}."
            )
        return response

    def search_read(
        self,
        model: str,
        domain: list[Any],
        fields: list[str],
        *,
        offset: int = 0,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        response = self._call(
            model,
            "search_read",
            {
                "domain": domain,
                "fields": fields,
                "offset": offset,
                "limit": limit,
                "order": "id asc",
            },
        )
        if not isinstance(response, list):
            raise OdooFetchError(
                f"Odoo returned an invalid employee record list for {model}."
            )
        return response


class OdooLegacyRpcAdapter(OdooAdapter):
    name = "XML-RPC"

    def __init__(self, config: OdooConfig):
        self.config = config

    def _server(self, endpoint: str) -> xmlrpc.client.ServerProxy:
        return xmlrpc.client.ServerProxy(
            f"{self.config.base_url}/xmlrpc/2/{endpoint}",
            allow_none=True,
        )

    def _authenticate(self) -> int:
        try:
            uid = self._server("common").authenticate(
                self.config.database,
                self.config.username,
                self.config.api_key,
                {},
            )
        except (xmlrpc.client.ProtocolError, xmlrpc.client.ResponseError) as exc:
            raise OdooUnavailableError(
                f"Odoo XML-RPC was unavailable: {type(exc).__name__}"
            ) from exc
        except OSError as exc:
            raise OdooUnavailableError(
                f"Could not reach Odoo XML-RPC: {type(exc).__name__}"
            ) from exc
        if not uid:
            raise OdooAuthenticationError(
                "Odoo rejected the username and API key or password."
            )
        return int(uid)

    def test_connection(self) -> dict[str, Any]:
        uid = self._authenticate()
        count = self.search_count("hr.employee", [])
        fields = self.fields_get("hr.employee")
        return {
            "authenticated_uid": uid,
            "employee_model_access": "available",
            "employee_count": count,
            "available_employee_fields": sorted(fields),
        }

    def fields_get(self, model: str) -> dict[str, dict[str, Any]]:
        uid = self._authenticate()
        try:
            return self._server("object").execute_kw(
                self.config.database,
                uid,
                self.config.api_key,
                model,
                "fields_get",
                [],
                {
                    "attributes": ["string", "help", "type", "relation"],
                },
            )
        except (xmlrpc.client.Fault, xmlrpc.client.ProtocolError) as exc:
            raise OdooPermissionError(
                f"Odoo denied access to field metadata for {model}."
            ) from exc

    def search_count(self, model: str, domain: list[Any]) -> int:
        uid = self._authenticate()
        try:
            return int(
                self._server("object").execute_kw(
                    self.config.database,
                    uid,
                    self.config.api_key,
                    model,
                    "search_count",
                    [domain],
                    {},
                )
            )
        except (xmlrpc.client.Fault, xmlrpc.client.ProtocolError) as exc:
            raise OdooPermissionError(
                f"Odoo denied access to {model}."
            ) from exc

    def search_read(
        self,
        model: str,
        domain: list[Any],
        fields: list[str],
        *,
        offset: int = 0,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        uid = self._authenticate()
        try:
            records = self._server("object").execute_kw(
                self.config.database,
                uid,
                self.config.api_key,
                model,
                "search_read",
                [domain],
                {
                    "fields": fields,
                    "offset": offset,
                    "limit": limit,
                    "order": "id asc",
                },
            )
        except (xmlrpc.client.Fault, xmlrpc.client.ProtocolError) as exc:
            raise OdooPermissionError(
                f"Odoo denied access to employee records."
            ) from exc
        if not isinstance(records, list):
            raise OdooFetchError("Odoo returned invalid employee records.")
        return records


class OdooClient:
    def __init__(
        self,
        config: OdooConfig | None = None,
        *,
        adapter: OdooAdapter | None = None,
    ):
        self.config = config or OdooConfig.from_env()
        self.adapter = adapter

    def select_adapter(self) -> OdooAdapter:
        if self.adapter is not None:
            return self.adapter
        version = detect_odoo_version(self.config)
        major = version["major"]
        if major not in SUPPORTED_MAJOR_VERSIONS:
            raise OdooUnavailableError(
                f"Odoo {major}.0 is outside the supported compatibility range "
                "(17 through 20)."
            )

        if major >= 19:
            json2 = OdooJson2Adapter(self.config)
            try:
                json2.test_connection()
                self.adapter = json2
                return json2
            except (OdooAuthenticationError, OdooUnavailableError, OdooFetchError):
                pass

        legacy = OdooLegacyRpcAdapter(self.config)
        legacy.test_connection()
        self.adapter = legacy
        return legacy

    def test_connection(self) -> dict[str, Any]:
        version = detect_odoo_version(self.config)
        major = version["major"]
        if major not in SUPPORTED_MAJOR_VERSIONS:
            raise OdooUnavailableError(
                f"Odoo {major}.0 is outside the supported compatibility range "
                "(17 through 20)."
            )
        adapter = self.select_adapter()
        diagnostic = adapter.test_connection()
        return {
            "success": True,
            "server_version": version["server_version"],
            "server_serie": version["server_serie"],
            "database": self.config.database,
            "selected_adapter": adapter.name,
            **diagnostic,
        }

    def get_companies(self) -> list[dict[str, Any]]:
        adapter = self.select_adapter()
        fields = ["id", "name"]
        records = adapter.search_read("res.company", [], fields, limit=500)
        return [
            {"id": int(record["id"]), "name": str(record.get("name") or "")}
            for record in records
            if isinstance(record, dict) and record.get("id")
        ]

    def discover_employee_fields(self) -> dict[str, dict[str, Any]]:
        adapter = self.select_adapter()
        return adapter.fields_get("hr.employee")

    def fetch_employees(
        self,
        *,
        include_archived: bool = False,
        odoo_company_id: int | None = None,
        employee_ids: Iterable[int] | None = None,
        page_size: int = 500,
        max_records: int | None = None,
    ) -> dict[str, Any]:
        if page_size <= 0 or (max_records is not None and max_records <= 0):
            raise OdooFetchError("Odoo pagination limits must be positive.")
        adapter = self.select_adapter()
        field_metadata = adapter.fields_get("hr.employee")
        preferred_fields = [
            "id",
            "name",
            "work_email",
            "department_id",
            "job_id",
            "parent_id",
            "active",
            "work_phone",
            "mobile_phone",
            "identification_id",
            "barcode",
            "job_title",
            "create_date",
            "write_date",
            "contract_date_start",
            "contract_type_id",
            "employee_type",
        ]
        fields = [
            field
            for field in preferred_fields
            if field in field_metadata
        ]
        if "id" not in fields:
            fields.insert(0, "id")

        domain: list[Any] = []
        if not include_archived:
            domain.append(["active", "=", True])
        if odoo_company_id is not None:
            domain.append(["company_id", "=", odoo_company_id])
        selected_ids = sorted({int(value) for value in (employee_ids or [])})
        if selected_ids:
            domain.append(["id", "in", selected_ids])

        total = adapter.search_count("hr.employee", domain)
        if max_records is not None and total > max_records:
            raise OdooFetchError(
                f"The Odoo selection exceeds the {max_records:,}-record limit."
            )

        records: list[dict[str, Any]] = []
        offset = 0
        seen_ids: set[int] = set()
        while offset < total:
            page_limit = (
                page_size
                if max_records is None
                else min(page_size, max_records - offset)
            )
            page = adapter.search_read(
                "hr.employee",
                domain,
                fields,
                offset=offset,
                limit=page_limit,
            )
            if not page:
                break
            for record in page:
                record_id = record.get("id")
                if isinstance(record_id, int) and record_id not in seen_ids:
                    seen_ids.add(record_id)
                    records.append(record)
            offset += len(page)
            if len(page) < page_limit:
                break

        if len(records) != total:
            raise OdooFetchError(
                "Odoo pagination returned an incomplete employee list "
                f"({len(records)} of {total} records)."
            )
        return {
            "records": records,
            "fields": fields,
            "available_fields": field_metadata,
            "total": total,
        }


def normalize_odoo_employees(
    records: Iterable[dict[str, Any]],
    *,
    odoo_database: str,
) -> tuple[list[str], list[dict[str, Any]], dict[str, str | None]]:
    columns = [
        "employee_id",
        "full_name",
        "email",
        "department",
        "job_title",
        "manager_name",
        "employment_status",
        "hire_date",
        "employment_type",
        "job_level",
        "_odoo_source_reference",
        "_odoo_employee_id_generated",
    ]
    rows = []
    for record in records:
        record_id = int(record["id"])
        identification = record.get("identification_id")
        barcode = record.get("barcode")
        employee_id = (
            str(identification).strip()
            if identification not in (None, False, "")
            else str(barcode).strip()
            if barcode not in (None, False, "")
            else f"ODOO-{record_id}"
        )
        full_name = str(record.get("name") or "").strip()
        email = str(record.get("work_email") or "").strip()
        department = _relation_name(record.get("department_id"))
        job_title = _relation_name(record.get("job_id"))
        if not job_title:
            job_title = str(record.get("job_title") or "").strip() or None
        manager_name = _relation_name(record.get("parent_id"))
        active = record.get("active")
        employment_status = "Active" if active is not False else "Archived"
        employment_type = _relation_name(record.get("contract_type_id"))
        if not employment_type:
            value = record.get("employee_type")
            employment_type = str(value).strip() if value not in (None, False) else None

        contract_start_date = record.get("contract_date_start")

        job_level = record.get("job_level")
        if isinstance(job_level, (list, dict)):
            job_level = _relation_name(job_level)
        elif job_level not in (None, False):
            job_level = str(job_level).strip()
        else:
            job_level = None

        source_reference = f"{odoo_database}:{record_id}"
        row = {
            "employee_id": employee_id,
            "full_name": full_name,
            "email": email,
            "department": department,
            "job_title": job_title,
            "manager_name": manager_name,
            "employment_status": employment_status,
            "hire_date": None,
            "employment_type": employment_type,
            "job_level": job_level,
            "_odoo_source_reference": source_reference,
            "_odoo_employee_id_generated": (
                employee_id.startswith("ODOO-")
            ),
        }
        if contract_start_date not in (None, False, ""):
            columns.append("contract_start_date")
            row["contract_start_date"] = str(contract_start_date).strip()
        create_date = record.get("create_date")
        if create_date not in (None, False):
            columns.append("odoo_create_date")
            row["odoo_create_date"] = str(create_date).strip()[:10]
        write_date = record.get("write_date")
        if write_date not in (None, False):
            columns.append("odoo_write_date")
            row["odoo_write_date"] = str(write_date).strip()
        rows.append(row)

    mapping = {
        "employee_id": "employee_id",
        "full_name": "full_name",
        "email": "email",
        "department": "department",
        "job_title": "job_title",
        "manager_name": "manager_name",
        "employment_status": "employment_status",
        "hire_date": "hire_date",
        "employment_type": "employment_type",
        "job_level": "job_level" if any(row["job_level"] for row in rows) else None,
        "_odoo_employee_id_generated": None,
        "_odoo_source_reference": None,
        "odoo_create_date": None,
    }
    if "contract_start_date" in columns:
        mapping["contract_start_date"] = None
    if "odoo_write_date" in columns:
        mapping["odoo_write_date"] = None
    return list(dict.fromkeys(columns)), rows, mapping
