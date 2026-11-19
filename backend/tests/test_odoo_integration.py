import json
from datetime import date

import pytest
import requests

import backend.app.services.odoo_client as odoo_module
from backend.app.services.employee_import_pipeline import (
    build_employee_import_preview,
)
from backend.app.services.odoo_client import (
    OdooAuthenticationError,
    OdooClient,
    OdooConfig,
    OdooConfigurationError,
    OdooJson2Adapter,
    OdooLegacyRpcAdapter,
    OdooUnavailableError,
    normalize_odoo_employees,
)


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("No JSON")
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(response=self)


class MockOdooAdapter:
    name = "Mock"

    def __init__(self):
        self.fields = {
            "id": {"type": "integer"},
            "name": {"type": "char"},
            "work_email": {"type": "char"},
            "department_id": {"type": "many2one", "relation": "hr.department"},
            "job_id": {"type": "many2one", "relation": "hr.job"},
            "parent_id": {"type": "many2one", "relation": "hr.employee"},
            "active": {"type": "boolean"},
            "identification_id": {"type": "char"},
            "barcode": {"type": "char"},
        }
        self.records = [
            {
                "id": 101,
                "name": "Ahmed Hassan",
                "work_email": "ahmed.odoo@example.com",
                "department_id": [10, "Engineering"],
                "job_id": [20, "Software Engineer"],
                "parent_id": False,
                "active": True,
                "identification_id": "EMP-A",
                "barcode": False,
            },
            {
                "id": 102,
                "name": "Sara Mohamed",
                "work_email": "sara.odoo@example.com",
                "department_id": [10, "Engineering"],
                "job_id": [21, "AI Engineer"],
                "parent_id": [101, "Ahmed Hassan"],
                "active": True,
                "identification_id": False,
                "barcode": "EMP-B",
            },
        ]

    def test_connection(self):
        return {
            "employee_model_access": "available",
            "employee_count": len(self.records),
            "available_employee_fields": sorted(self.fields),
        }

    def fields_get(self, model):
        return self.fields

    def search_count(self, model, domain):
        return len(self.records)

    def search_read(self, model, domain, fields, offset=0, limit=500):
        return self.records[offset:offset + limit]


def test_config_requires_safe_environment(monkeypatch):
    monkeypatch.delenv("ODOO_BASE_URL", raising=False)
    monkeypatch.delenv("ODOO_DATABASE", raising=False)
    monkeypatch.delenv("ODOO_USERNAME", raising=False)
    monkeypatch.delenv("ODOO_API_KEY", raising=False)
    with pytest.raises(OdooConfigurationError, match="Missing Odoo"):
        OdooConfig.from_env()


def test_config_accepts_localhost_http(monkeypatch):
    monkeypatch.setenv("ODOO_BASE_URL", "http://localhost:8069")
    monkeypatch.setenv("ODOO_DATABASE", "odoo_training_test")
    monkeypatch.setenv("ODOO_USERNAME", "integration")
    monkeypatch.setenv("ODOO_API_KEY", "test-key")
    monkeypatch.setenv("ODOO_API_TIMEOUT", "30")
    config = OdooConfig.from_env()
    assert config.database == "odoo_training_test"
    assert config.safe_status()["api_key_configured"] is True
    assert "test-key" not in repr(config.safe_status())


def test_config_rejects_remote_http(monkeypatch):
    monkeypatch.setenv("ODOO_BASE_URL", "http://odoo.example.test")
    monkeypatch.setenv("ODOO_DATABASE", "odoo")
    monkeypatch.setenv("ODOO_USERNAME", "integration")
    monkeypatch.setenv("ODOO_API_KEY", "test-key")
    with pytest.raises(OdooConfigurationError, match="HTTPS"):
        OdooConfig.from_env()


def test_json2_request_construction(monkeypatch):
    config = OdooConfig(
        "https://odoo.example.test",
        "odoo",
        "integration",
        "secret-key",
        30,
    )
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse(
            payload=[
                {"id": 101, "name": "Ahmed Hassan"},
            ],
        )

    monkeypatch.setattr(odoo_module.requests, "post", fake_post)
    records = OdooJson2Adapter(config).search_read(
        "hr.employee",
        [["active", "=", True]],
        ["id", "name"],
        offset=10,
        limit=25,
    )
    assert captured["url"].endswith("/json/2/hr.employee/search_read")
    assert captured["headers"]["Authorization"] == "bearer secret-key"
    assert captured["headers"]["X-Odoo-Database"] == "odoo"
    assert captured["json"]["offset"] == 10
    assert captured["json"]["limit"] == 25
    assert records[0]["name"] == "Ahmed Hassan"


def test_json2_authentication_failure(monkeypatch):
    config = OdooConfig(
        "https://odoo.example.test",
        "odoo",
        "integration",
        "bad-key",
        30,
    )
    monkeypatch.setattr(
        odoo_module.requests,
        "post",
        lambda *args, **kwargs: FakeResponse(
            status_code=401,
            payload={"message": "Invalid apikey"},
        ),
    )
    with pytest.raises(OdooAuthenticationError):
        OdooJson2Adapter(config).search_count("hr.employee", [])


def test_legacy_rpc_authentication_and_request_shape(monkeypatch):
    config = OdooConfig(
        "http://localhost:8069",
        "odoo_training_test",
        "integration",
        "legacy-key",
        30,
    )
    adapter = OdooLegacyRpcAdapter(config)

    class Common:
        def authenticate(self, database, username, api_key, context):
            assert (database, username, api_key) == (
                "odoo_training_test",
                "integration",
                "legacy-key",
            )
            return 7

    class Object:
        def execute_kw(
            self,
            database,
            uid,
            api_key,
            model,
            method,
            args,
            kwargs,
        ):
            assert database == "odoo_training_test"
            assert uid == 7
            assert api_key == "legacy-key"
            assert model == "hr.employee"
            assert method == "search_read"
            assert args == [[["active", "=", True]]]
            assert kwargs["offset"] == 20
            assert kwargs["limit"] == 50
            return [{"id": 101, "name": "Ahmed Hassan"}]

    monkeypatch.setattr(
        adapter,
        "_server",
        lambda endpoint: Common() if endpoint == "common" else Object(),
    )
    records = adapter.search_read(
        "hr.employee",
        [["active", "=", True]],
        ["id", "name"],
        offset=20,
        limit=50,
    )
    assert records == [{"id": 101, "name": "Ahmed Hassan"}]


def test_version_detection_and_unsupported_version(monkeypatch):
    config = OdooConfig(
        "https://odoo.example.test",
        "odoo",
        "integration",
        "key",
        30,
    )
    monkeypatch.setattr(
        odoo_module.requests,
        "post",
        lambda *args, **kwargs: FakeResponse(
            payload={
                "result": {
                    "server_version": "19.0",
                    "server_serie": "19.0",
                    "server_version_info": [19, 0, 0, "final", 0],
                }
            }
        ),
    )
    assert odoo_module.detect_odoo_version(config)["major"] == 19

    monkeypatch.setattr(
        odoo_module,
        "detect_odoo_version",
        lambda unused: {
            "server_version": "16.0",
            "server_serie": "16.0",
            "major": 16,
        },
    )
    with pytest.raises(OdooUnavailableError, match="outside"):
        OdooClient(config, adapter=None).select_adapter()


def test_normalization_maps_relationships_and_preserves_source_reference():
    adapter = MockOdooAdapter()
    columns, rows, mapping = normalize_odoo_employees(
        adapter.records,
        odoo_database="odoo_training_test",
    )
    assert "full_name" in columns
    assert rows[0]["department"] == "Engineering"
    assert rows[0]["job_title"] == "Software Engineer"
    assert rows[1]["manager_name"] == "Ahmed Hassan"
    assert rows[0]["employee_id"] == "EMP-A"
    assert rows[1]["employee_id"] == "EMP-B"
    assert rows[0]["_odoo_source_reference"] == (
        "odoo_training_test:101"
    )
    assert mapping["full_name"] == "full_name"


def test_generated_employee_id_is_visible_not_silent():
    columns, rows, mapping = normalize_odoo_employees(
        [{
            "id": 303,
            "name": "No Identifier",
            "work_email": "no-id@example.test",
            "department_id": [10, "Engineering"],
            "job_id": [20, "Engineer"],
            "parent_id": False,
            "active": True,
        }],
        odoo_database="odoo_training_test",
    )
    assert rows[0]["employee_id"] == "ODOO-303"
    assert rows[0]["_odoo_employee_id_generated"] is True
    assert "_odoo_source_reference" in columns


def test_o_auth_empty_optional_fields_do_not_create_fake_values():
    _, rows, _ = normalize_odoo_employees(
        [{
            "id": 304,
            "name": "Optional Employee",
            "work_email": False,
            "department_id": False,
            "job_id": False,
            "parent_id": False,
            "active": False,
        }],
        odoo_database="odoo_training_test",
    )
    assert rows[0]["email"] == ""
    assert rows[0]["department"] is None
    assert rows[0]["job_title"] is None
    assert rows[0]["manager_name"] is None
    assert rows[0]["employment_status"] == "Archived"
    assert rows[0]["employment_type"] is None
