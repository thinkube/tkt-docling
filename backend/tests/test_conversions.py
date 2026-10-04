# Copyright Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: MIT

"""The conversions API, with storage and Argo Workflows replaced by doubles.

What reaches storage and what is submitted to Argo is recorded, and the
workflow's phase is set by each test.
"""
import json

import pytest
from fastapi.testclient import TestClient

from app.core.api_tokens import get_current_user_dual_auth
from app.services import storage, workflows

PDF = b"%PDF-1.7\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF\n"


class FakeCloud:
    def __init__(self):
        self.objects = {}
        self.submitted = []
        self.phases = {}

    def put_source(self, conversion_id, data):
        self.objects[storage.source_key(conversion_id)] = data

    def open_output(self, conversion_id, filename):
        key = f"{storage.outputs_key(conversion_id)}/{filename}"
        if key not in self.objects:
            return None
        return iter([self.objects[key]])

    def read_result(self, conversion_id):
        chunks = self.open_output(conversion_id, "result.json")
        return None if chunks is None else json.loads(b"".join(chunks))

    def delete_conversion(self, conversion_id):
        prefix = storage.conversion_prefix(conversion_id) + "/"
        for key in [k for k in self.objects if k.startswith(prefix)]:
            del self.objects[key]

    def submit(self, conversion_id, pipeline, formats):
        name = f"docling-test-convert-{len(self.submitted)}"
        self.submitted.append((conversion_id, pipeline, formats))
        self.phases[name] = workflows.WorkflowState("Pending", None)
        return name

    def state(self, name):
        return self.phases.get(name)

    def finish(self, conversion_id, outputs):
        for filename, content in outputs.items():
            self.objects[f"{storage.outputs_key(conversion_id)}/{filename}"] = content


@pytest.fixture
def cloud(monkeypatch):
    fake = FakeCloud()
    for name in ("put_source", "open_output", "read_result", "delete_conversion"):
        monkeypatch.setattr(storage, name, getattr(fake, name))
    monkeypatch.setattr(workflows, "submit", fake.submit)
    monkeypatch.setattr(workflows, "state", fake.state)
    return fake


@pytest.fixture
def user(client: TestClient):
    identity = {"sub": "user-1", "preferred_username": "tester", "auth_method": "keycloak"}
    client.app.dependency_overrides[get_current_user_dual_auth] = lambda: identity
    yield identity
    client.app.dependency_overrides.pop(get_current_user_dual_auth, None)


def upload(client, pipeline="standard", formats="markdown,jats", content=PDF, filename="paper.pdf"):
    return client.post(
        "/api/v1/conversions",
        data={"pipeline": pipeline, "formats": formats},
        files={"file": (filename, content, "application/pdf")},
    )


def test_requires_authentication(client: TestClient):
    assert client.get("/api/v1/conversions").status_code == 401


def test_options_list_formats_and_pipelines(client, user):
    response = client.get("/api/v1/conversions/options")
    assert response.status_code == 200
    data = response.json()
    assert [f["name"] for f in data["formats"]] == ["markdown", "html", "text", "json", "doctags", "jats"]
    assert {p["name"]: p["available"] for p in data["pipelines"]} == {"standard": True, "granite-docling": True}


def test_upload_stores_pdf_and_submits_workflow(client, user, cloud):
    response = upload(client)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["status"] == "queued"
    assert data["formats"] == ["markdown", "jats"]
    assert data["workflow_name"] == "docling-test-convert-0"
    assert data["logs_url"].endswith("/docling-test-convert-0")

    assert cloud.objects[storage.source_key(data["id"])] == PDF
    assert cloud.submitted == [(data["id"], "standard", ["markdown", "jats"])]


def test_refuses_what_is_not_a_pdf(client, user, cloud):
    response = upload(client, content=b"hello", filename="notes.txt")
    assert response.status_code == 422
    assert "not a PDF" in response.json()["detail"]
    assert cloud.submitted == []


def test_refuses_unknown_format_and_pipeline(client, user, cloud):
    assert upload(client, formats="markdown,docx").status_code == 422
    assert upload(client, pipeline="ocr").status_code == 422
    assert cloud.submitted == []


def test_granite_needs_the_gateway_token(client, user, cloud, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "THINKUBE_API_TOKEN", None)
    response = upload(client, pipeline="granite-docling")
    assert response.status_code == 409
    assert "THINKUBE_API_TOKEN" in response.json()["detail"]

    options = client.get("/api/v1/conversions/options").json()
    granite = next(p for p in options["pipelines"] if p["name"] == "granite-docling")
    assert granite["available"] is False


def test_status_follows_the_workflow_and_outputs_download(client, user, cloud):
    conversion = upload(client).json()
    name = conversion["workflow_name"]

    cloud.phases[name] = workflows.WorkflowState("Running", None)
    assert client.get(f"/api/v1/conversions/{conversion['id']}").json()["status"] == "running"
    assert client.get(f"/api/v1/conversions/{conversion['id']}/outputs/jats").status_code == 409

    cloud.finish(conversion["id"], {
        "document.md": b"# Title\n",
        "document.jats.xml": b"<article/>",
        "result.json": json.dumps({"pages": 15, "seconds": 14.0, "errors": []}).encode(),
    })
    cloud.phases[name] = workflows.WorkflowState("Succeeded", None)
    done = client.get(f"/api/v1/conversions/{conversion['id']}").json()
    assert (done["status"], done["pages"], done["seconds"]) == ("succeeded", 15, 14.0)
    assert done["finished_at"] is not None

    md = client.get(f"/api/v1/conversions/{conversion['id']}/outputs/markdown?download=true")
    assert md.status_code == 200
    assert md.content == b"# Title\n"
    assert md.headers["content-disposition"] == 'attachment; filename="paper.md"'

    jats = client.get(f"/api/v1/conversions/{conversion['id']}/outputs/jats")
    assert jats.headers["content-type"].startswith("application/xml")
    assert jats.headers["content-disposition"] == 'inline; filename="paper.jats.xml"'

    assert client.get(f"/api/v1/conversions/{conversion['id']}/outputs/html").status_code == 404


def test_failed_workflow_keeps_its_message(client, user, cloud):
    conversion = upload(client).json()
    cloud.phases[conversion["workflow_name"]] = workflows.WorkflowState("Failed", "OOMKilled (exit code 137)")
    data = client.get(f"/api/v1/conversions/{conversion['id']}").json()
    assert data["status"] == "failed"
    assert data["error"] == "OOMKilled (exit code 137)"


def test_removed_workflow_is_settled_from_storage(client, user, cloud):
    conversion = upload(client).json()
    del cloud.phases[conversion["workflow_name"]]
    cloud.finish(conversion["id"], {"result.json": json.dumps({"pages": 2, "seconds": 3.0, "errors": []}).encode()})
    assert client.get(f"/api/v1/conversions/{conversion['id']}").json()["status"] == "succeeded"


def test_conversions_are_private_to_their_owner(client, user, cloud):
    conversion = upload(client).json()
    client.app.dependency_overrides[get_current_user_dual_auth] = lambda: {"sub": "someone-else"}
    assert client.get(f"/api/v1/conversions/{conversion['id']}").status_code == 404
    assert client.get("/api/v1/conversions").json() == []


def test_delete_removes_row_and_files(client, user, cloud):
    conversion = upload(client).json()
    assert client.delete(f"/api/v1/conversions/{conversion['id']}").status_code == 204
    assert client.get(f"/api/v1/conversions/{conversion['id']}").status_code == 404
    assert cloud.objects == {}
