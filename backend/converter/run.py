"""Convert one PDF: the command a conversion step runs.

    python -m converter.run --input source.pdf --output out/ \
        --pipeline standard --formats markdown,jats

Writes one file per format into the output directory, named as FORMATS
declares, and result.json with the page count, the time taken and Docling's
status. Exits non-zero when the conversion fails, so the step fails with
Docling's own message in its log.

The standard pipeline reads its models from DOCLING_ARTIFACTS_PATH and
stops when they are not there.

The granite-docling pipeline reads three variables: LLM_GATEWAY_URL,
THINKUBE_API_TOKEN and GRANITE_DOCLING_MODEL. A missing one stops the run
before any page is sent.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

from converter.formats import FORMATS, PIPELINES

GRANITE_ENV = ("LLM_GATEWAY_URL", "THINKUBE_API_TOKEN", "GRANITE_DOCLING_MODEL")


def build_converter(pipeline: str, env=os.environ):
    from docling.datamodel.base_models import InputFormat
    from docling.document_converter import DocumentConverter, PdfFormatOption

    if pipeline == "standard":
        from docling.datamodel.pipeline_options import PdfPipelineOptions

        from converter.models import REQUIRED

        artifacts = env.get("DOCLING_ARTIFACTS_PATH")
        if not artifacts or not (Path(artifacts) / REQUIRED).is_dir():
            raise SystemExit(
                f"The standard pipeline reads its models from DOCLING_ARTIFACTS_PATH ({artifacts!r}), "
                f"which has no {REQUIRED}. The workflow step receives them from Thinkube Storage."
            )

        options = PdfPipelineOptions(do_ocr=False, do_table_structure=True)
        return DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)})

    if pipeline == "granite-docling":
        from docling.datamodel.pipeline_options import VlmPipelineOptions
        from docling.datamodel.pipeline_options_vlm_model import ApiVlmOptions, ResponseFormat
        from docling.datamodel.vlm_prompts import DOCLING_BASE_PAGE_PROMPT
        from docling.pipeline.vlm_pipeline import VlmPipeline

        missing = [name for name in GRANITE_ENV if not env.get(name)]
        if missing:
            raise SystemExit(
                f"The granite-docling pipeline needs {', '.join(missing)}. "
                "THINKUBE_API_TOKEN comes from the Secrets page of thinkube-control; "
                "LLM_GATEWAY_URL and GRANITE_DOCLING_MODEL from thinkube.yaml."
            )
        options = VlmPipelineOptions(enable_remote_services=True)
        options.vlm_options = ApiVlmOptions(
            url=f"{env['LLM_GATEWAY_URL'].rstrip('/')}/v1/chat/completions",
            headers={"Authorization": f"Bearer {env['THINKUBE_API_TOKEN']}"},
            # DocTags are special tokens of this model: the server must keep them.
            params={"model": env["GRANITE_DOCLING_MODEL"], "max_tokens": 4096, "skip_special_tokens": False},
            prompt=DOCLING_BASE_PAGE_PROMPT,
            timeout=180,
            scale=2.0,
            temperature=0.0,
            concurrency=4,
            stop_strings=["</doctag>", "<|end_of_text|>"],
            response_format=ResponseFormat.DOCTAGS,
        )
        return DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_cls=VlmPipeline, pipeline_options=options)}
        )

    raise SystemExit(f"Unknown pipeline '{pipeline}'. Known: {', '.join(PIPELINES)}")


def parse_formats(value: str):
    names = [n.strip() for n in value.split(",") if n.strip()]
    unknown = [n for n in names if n not in FORMATS]
    if not names or unknown:
        raise argparse.ArgumentTypeError(
            f"formats must be a comma-separated list of {', '.join(FORMATS)}; got {value!r}"
        )
    return names


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--pipeline", required=True, choices=sorted(PIPELINES))
    parser.add_argument("--formats", required=True, type=parse_formats)
    args = parser.parse_args(argv)

    from docling.datamodel.base_models import ConversionStatus

    converter = build_converter(args.pipeline)
    started = time.monotonic()
    result = converter.convert(args.input, raises_on_error=False)
    seconds = round(time.monotonic() - started, 1)

    errors = [f"{e.component_type}: {e.error_message}" for e in result.errors]
    for line in errors:
        print(line, file=sys.stderr)
    if result.status not in (ConversionStatus.SUCCESS, ConversionStatus.PARTIAL_SUCCESS):
        print(f"Conversion {result.status.value} after {seconds}s", file=sys.stderr)
        return 1

    args.output.mkdir(parents=True, exist_ok=True)
    for name in args.formats:
        fmt = FORMATS[name]
        (args.output / fmt.filename).write_text(fmt.export(result.document), encoding="utf-8")

    summary = {
        "status": result.status.value,
        "pipeline": args.pipeline,
        "formats": args.formats,
        "pages": len(result.pages),
        "seconds": seconds,
        "errors": errors,
    }
    (args.output / "result.json").write_text(json.dumps(summary), encoding="utf-8")
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
