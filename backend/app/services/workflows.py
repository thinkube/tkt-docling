# Copyright Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: MIT

"""Conversions as Argo workflows, in this application's own namespace.

One workflow per conversion: `python -m converter.run` in this application's
backend image. The step reads the PDF from the artifact repository by key and
writes the output directory back under another key, so it needs no storage
credentials. The granite-docling step also reads THINKUBE_API_TOKEN from the
application's Secret.

A standard step also receives the Docling models by key. While they are not
yet in storage, the workflow first runs `python -m converter.models`, which
downloads them into that key.
"""
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from hera.exceptions import NotFound
from hera.workflows import (
    Container,
    Env,
    NoneArchiveStrategy,
    Resources,
    S3Artifact,
    SecretEnvFrom,
    Steps,
    Workflow,
    WorkflowsService,
)
from hera.workflows.models import TTLStrategy

from app.core.config import settings
from app.services import storage
from converter.models import READY_MARKER

SERVICE_ACCOUNT_TOKEN = Path("/var/run/secrets/kubernetes.io/serviceaccount/token")

# The standard pipeline runs the layout and table models on CPU: about 2 GB
# at its peak on a 15-page paper. Granite-Docling runs on the gateway; the
# step only renders pages and waits for answers.
STEP_RESOURCES = {
    "standard": Resources(cpu_request=1, cpu_limit=2, memory_request="2Gi", memory_limit="4Gi"),
    "granite-docling": Resources(cpu_request="500m", cpu_limit=1, memory_request="1Gi", memory_limit="2Gi"),
}

WORK_DIR = "/tmp/conversion"
MODELS_DIR = "/opt/docling-models"
PREPARE_RESOURCES = Resources(cpu_request="250m", cpu_limit=1, memory_request="512Mi", memory_limit="1Gi")
# Argo's wait container uploads the step's outputs within the executor limit
# the workflow controller sets for every step (256Mi on Thinkube), which the
# upload of a 200 MB model file exceeds. The prepare step raises it for itself.
PREPARE_WAIT_PATCH = json.dumps(
    {"containers": [{"name": "wait", "resources": {"requests": {"memory": "256Mi"}, "limits": {"memory": "1Gi"}}}]}
)


@dataclass
class WorkflowState:
    phase: str  # Pending, Running, Succeeded, Failed, Error
    message: Optional[str]


def _service() -> WorkflowsService:
    return WorkflowsService(
        host=settings.WORKFLOWS_SERVER_URL,
        verify_ssl=False,
        token=SERVICE_ACCOUNT_TOKEN.read_text(),
        namespace=settings.WORKFLOWS_NAMESPACE,
    )


def build_workflow(conversion_id: str, pipeline: str, formats: list[str], prepare_models: bool = False) -> Workflow:
    """The conversion's workflow; with prepare_models, a first step puts the models in storage."""
    env = []
    env_from = []
    inputs = [S3Artifact(name="source", path=f"{WORK_DIR}/source.pdf", key=storage.source_key(conversion_id))]
    if pipeline == "granite-docling":
        env = [
            Env(name="LLM_GATEWAY_URL", value=settings.LLM_GATEWAY_URL),
            Env(name="GRANITE_DOCLING_MODEL", value=settings.GRANITE_DOCLING_MODEL),
        ]
        env_from = [SecretEnvFrom(name=f"{settings.APP_NAME}-secrets")]
    else:
        inputs.append(S3Artifact(name="models", path=MODELS_DIR, key=storage.models_key()))
        # The models come from the artifact; nothing is fetched from Hugging Face.
        env = [Env(name="DOCLING_ARTIFACTS_PATH", value=MODELS_DIR), Env(name="HF_HUB_OFFLINE", value="1")]

    with Workflow(
        generate_name=f"{settings.APP_NAME}-convert-",
        entrypoint="conversion",
        namespace=settings.WORKFLOWS_NAMESPACE,
        service_account_name=settings.WORKFLOWS_SERVICE_ACCOUNT,
        image_pull_secrets=["app-pull-secret"],
        labels={"thinkube.io/conversion": conversion_id},
        # A finished run is kept a day for its logs, then removed; the outputs
        # stay in storage until the conversion is deleted.
        ttl_strategy=TTLStrategy(seconds_after_completion=86400),
    ) as workflow:
        convert = Container(
            name="convert",
            image=settings.CONTAINER_IMAGE_BACKEND,
            command=["python", "-m", "converter.run"],
            args=[
                "--input", f"{WORK_DIR}/source.pdf",
                "--output", f"{WORK_DIR}/out",
                "--pipeline", pipeline,
                "--formats", ",".join(formats),
            ],
            env=env,
            env_from=env_from,
            resources=STEP_RESOURCES[pipeline],
            inputs=inputs,
            outputs=[
                S3Artifact(
                    name="outputs",
                    path=f"{WORK_DIR}/out",
                    key=storage.outputs_key(conversion_id),
                    archive=NoneArchiveStrategy(),
                )
            ],
        )
        if prepare_models:
            prepare = Container(
                name="prepare-models",
                image=settings.CONTAINER_IMAGE_BACKEND,
                command=["python", "-m", "converter.models"],
                args=["--output", "/tmp/models", "--marker", f"/tmp/ready/{READY_MARKER}"],
                resources=PREPARE_RESOURCES,
                pod_spec_patch=PREPARE_WAIT_PATCH,
                # Artifacts are uploaded in this order: the marker only after the models.
                outputs=[
                    S3Artifact(
                        name="models",
                        path="/tmp/models",
                        key=storage.models_key(),
                        archive=NoneArchiveStrategy(),
                    ),
                    S3Artifact(
                        name="ready",
                        path=f"/tmp/ready/{READY_MARKER}",
                        key=f"{storage.models_key()}/{READY_MARKER}",
                        archive=NoneArchiveStrategy(),
                    ),
                ],
            )
        with Steps(name="conversion"):
            if prepare_models:
                prepare(name="prepare-models")
            convert(name="convert")
    return workflow


def submit(conversion_id: str, pipeline: str, formats: list[str]) -> str:
    """Submit the conversion's workflow and return its name."""
    prepare = pipeline == "standard" and not storage.models_ready()
    workflow = build_workflow(conversion_id, pipeline, formats, prepare_models=prepare)
    workflow.workflows_service = _service()
    created = workflow.create()
    return created.metadata.name


def state(workflow_name: str) -> Optional[WorkflowState]:
    """The workflow's phase and message, or None when the workflow no longer exists."""
    try:
        wf = _service().get_workflow(name=workflow_name, namespace=settings.WORKFLOWS_NAMESPACE)
    except NotFound:
        return None
    status = wf.status
    # Argo leaves the phase empty until the controller has picked the run up.
    phase = (status.phase if status else None) or "Pending"
    message = status.message if status else None
    if phase in ("Failed", "Error") and status and status.nodes:
        # The step's own message says more than the workflow's summary.
        step_messages = [n.message for n in status.nodes.values() if n.type == "Pod" and n.message]
        if step_messages:
            message = step_messages[-1]
    return WorkflowState(phase=phase, message=message)


def logs_url(workflow_name: str) -> str:
    return f"{settings.WORKFLOWS_UI_URL}/{workflow_name}"
