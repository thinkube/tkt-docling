# Copyright Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: MIT

"""The workflow a conversion submits: steps in the backend image, artifacts by key."""
import json
import re
from pathlib import Path

from app.services import workflows
from converter.models import DOCLING_VERSION


def spec_of(pipeline, prepare_models=False):
    return workflows.build_workflow("c-1", pipeline, ["markdown", "jats"], prepare_models).to_dict()["spec"]


def template(spec, name):
    return next(t for t in spec["templates"] if t["name"] == name)


def steps(spec):
    return [s[0]["name"] for s in template(spec, "conversion")["steps"]]


def test_convert_runs_the_converter_in_the_backend_image():
    spec = spec_of("standard")
    container = template(spec, "convert")["container"]
    assert container["image"] == "registry.test.invalid/thinkube/docling-test-backend:latest"
    assert container["command"] == ["python", "-m", "converter.run"]
    assert container["args"][-4:] == ["--pipeline", "standard", "--formats", "markdown,jats"]
    assert spec["serviceAccountName"] == "docling-test-workflows"
    assert container["resources"]["limits"]["memory"] == "4Gi"
    assert steps(spec) == ["convert"]


def test_artifacts_are_keys_in_the_default_repository():
    convert = template(spec_of("standard"), "convert")
    source, models = convert["inputs"]["artifacts"]
    (outputs,) = convert["outputs"]["artifacts"]
    assert source["s3"] == {"key": "docling-test/conversions/c-1/source.pdf"}
    assert models == {"name": "models", "path": "/opt/docling-models",
                      "s3": {"key": f"docling-test/docling-models/{DOCLING_VERSION}"}}
    assert outputs["s3"] == {"key": "docling-test/conversions/c-1/outputs"}
    assert outputs["archive"] == {"none": {}}


def test_standard_step_is_offline_and_gets_no_secrets():
    container = template(spec_of("standard"), "convert")["container"]
    assert container["env"] == [
        {"name": "DOCLING_ARTIFACTS_PATH", "value": "/opt/docling-models"},
        {"name": "HF_HUB_OFFLINE", "value": "1"},
    ]
    assert "envFrom" not in container


def test_models_are_prepared_first_when_missing():
    spec = spec_of("standard", prepare_models=True)
    assert steps(spec) == ["prepare-models", "convert"]
    prepare = template(spec, "prepare-models")
    assert prepare["container"]["command"] == ["python", "-m", "converter.models"]
    models, ready = prepare["outputs"]["artifacts"]
    assert models["s3"] == {"key": f"docling-test/docling-models/{DOCLING_VERSION}"}
    assert ready["s3"] == {"key": f"docling-test/docling-models/{DOCLING_VERSION}/READY"}
    patch = json.loads(prepare["podSpecPatch"])
    assert patch["containers"][0]["name"] == "wait"
    assert patch["containers"][0]["resources"]["limits"]["memory"] == "1Gi"


def test_granite_step_gets_gateway_and_token_and_no_models():
    convert = template(spec_of("granite-docling"), "convert")
    container = convert["container"]
    env = {e["name"]: e["value"] for e in container["env"]}
    assert env == {
        "LLM_GATEWAY_URL": "http://llm-proxy.test.invalid:8080",
        "GRANITE_DOCLING_MODEL": "ibm-granite/granite-docling-258M",
    }
    assert container["envFrom"] == [{"secretRef": {"name": "docling-test-secrets"}}]
    assert [a["name"] for a in convert["inputs"]["artifacts"]] == ["source"]


def test_models_key_follows_the_installed_docling_version():
    requirements = (Path(__file__).parents[1] / "requirements-converter.txt").read_text()
    assert re.search(r"^docling-slim\[[^\]]*\]==([\d.]+)$", requirements, re.M).group(1) == DOCLING_VERSION
