# Copyright Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: MIT

"""The PDFs and the conversion outputs, in Thinkube Storage.

Both live in the bucket the namespace's Argo artifact repository uses, under
this application's prefix, so a workflow step reads and writes them by key
with no credentials of its own:

    argo-artifacts/<app>/conversions/<id>/source.pdf
    argo-artifacts/<app>/conversions/<id>/outputs/<file>
    argo-artifacts/<app>/docling-models/<docling version>/...
"""
import json
from functools import lru_cache
from typing import Iterator, Optional

import boto3
from botocore.exceptions import ClientError

from app.core.config import settings
from converter.models import DOCLING_VERSION, READY_MARKER

# The bucket of the artifact repository the platform writes for
# `services: [workflows]` (thinkube-control templates/k8s/workflows.j2).
ARTIFACT_BUCKET = "argo-artifacts"


@lru_cache
def _client():
    return boto3.client(
        "s3",
        endpoint_url=settings.SEAWEEDFS_ENDPOINT,
        aws_access_key_id=settings.SEAWEEDFS_ACCESS_KEY,
        aws_secret_access_key=settings.SEAWEEDFS_SECRET_KEY,
        region_name="us-east-1",
    )


def conversion_prefix(conversion_id: str) -> str:
    return f"{settings.APP_NAME}/conversions/{conversion_id}"


def source_key(conversion_id: str) -> str:
    return f"{conversion_prefix(conversion_id)}/source.pdf"


def outputs_key(conversion_id: str) -> str:
    return f"{conversion_prefix(conversion_id)}/outputs"


def models_key() -> str:
    return f"{settings.APP_NAME}/docling-models/{DOCLING_VERSION}"


def models_ready() -> bool:
    """Whether the models are in storage, complete: the READY marker is written last."""
    try:
        _client().head_object(Bucket=ARTIFACT_BUCKET, Key=f"{models_key()}/{READY_MARKER}")
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") in ("NoSuchKey", "404", "NotFound"):
            return False
        raise
    return True


def put_source(conversion_id: str, data: bytes) -> None:
    _client().put_object(
        Bucket=ARTIFACT_BUCKET, Key=source_key(conversion_id), Body=data, ContentType="application/pdf"
    )


def open_output(conversion_id: str, filename: str) -> Optional[Iterator[bytes]]:
    """The output file as chunks, or None when it does not exist."""
    try:
        obj = _client().get_object(Bucket=ARTIFACT_BUCKET, Key=f"{outputs_key(conversion_id)}/{filename}")
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
            return None
        raise
    return obj["Body"].iter_chunks(chunk_size=64 * 1024)


def read_result(conversion_id: str) -> Optional[dict]:
    """result.json written by the conversion step, or None when it does not exist."""
    chunks = open_output(conversion_id, "result.json")
    if chunks is None:
        return None
    return json.loads(b"".join(chunks))


def delete_conversion(conversion_id: str) -> None:
    client = _client()
    prefix = conversion_prefix(conversion_id) + "/"
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=ARTIFACT_BUCKET, Prefix=prefix):
        keys = [{"Key": o["Key"]} for o in page.get("Contents", [])]
        if keys:
            client.delete_objects(Bucket=ARTIFACT_BUCKET, Delete={"Objects": keys})
