# Copyright Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: MIT

"""The Docling models the standard pipeline reads, kept in Thinkube Storage.

They are downloaded once, by a workflow step, into the application's prefix
in the artifact bucket, and every standard conversion step receives them as
an input artifact at DOCLING_ARTIFACTS_PATH. The key carries the Docling
version, so an upgrade downloads the models that version expects.

    python -m converter.models --output /tmp/models --marker /tmp/ready/READY

downloads the layout and table models into --output and then writes the
marker. The workflow uploads the marker as a separate artifact after the
models, so its presence in storage means the models are complete.
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

# The version in requirements-converter.txt; tests/test_workflow_spec.py holds them equal.
DOCLING_VERSION = "2.128.0"
READY_MARKER = "READY"
MODELS = ("layout", "tableformer")
# The step runs the PyTorch layout model; the download also brings its ONNX copy.
UNUSED = ("docling-project--docling-layout-heron-onnx",)
# A directory every complete download contains.
REQUIRED = "docling-project--docling-models"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Download the Docling models the standard pipeline reads")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--marker", required=True, type=Path)
    args = parser.parse_args(argv)

    args.output.mkdir(parents=True, exist_ok=True)
    subprocess.run(["docling-tools", "models", "download", "-o", str(args.output), *MODELS], check=True)
    for name in UNUSED:
        if (args.output / name).exists():
            shutil.rmtree(args.output / name)
    args.marker.parent.mkdir(parents=True, exist_ok=True)
    args.marker.write_text(DOCLING_VERSION, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
