"""The workflow a conversion submits: one step in the backend image, artifacts by key."""
from app.services import workflows


def step(pipeline):
    spec = workflows.build_workflow("c-1", pipeline, ["markdown", "jats"]).to_dict()["spec"]
    (template,) = spec["templates"]
    return spec, template


def test_step_runs_the_converter_in_the_backend_image():
    spec, template = step("standard")
    container = template["container"]
    assert container["image"] == "registry.test.invalid/thinkube/docling-test-backend:latest"
    assert container["command"] == ["python", "-m", "converter.run"]
    assert container["args"][-4:] == ["--pipeline", "standard", "--formats", "markdown,jats"]
    assert spec["serviceAccountName"] == "docling-test-workflows"
    assert container["resources"]["limits"]["memory"] == "4Gi"


def test_artifacts_are_keys_in_the_default_repository():
    _, template = step("standard")
    (source,) = template["inputs"]["artifacts"]
    (outputs,) = template["outputs"]["artifacts"]
    assert source["s3"] == {"key": "docling-test/conversions/c-1/source.pdf"}
    assert outputs["s3"] == {"key": "docling-test/conversions/c-1/outputs"}
    assert outputs["archive"] == {"none": {}}


def test_standard_step_gets_no_secrets():
    _, template = step("standard")
    assert "envFrom" not in template["container"]


def test_granite_step_gets_gateway_and_token():
    _, template = step("granite-docling")
    container = template["container"]
    env = {e["name"]: e["value"] for e in container["env"]}
    assert env == {
        "LLM_GATEWAY_URL": "http://llm-proxy.test.invalid:8080",
        "GRANITE_DOCLING_MODEL": "ibm-granite/granite-docling-258M",
    }
    assert container["envFrom"] == [{"secretRef": {"name": "docling-test-secrets"}}]
