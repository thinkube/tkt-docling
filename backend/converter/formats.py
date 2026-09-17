"""The output formats a conversion can produce.

Each format is written from the same DoclingDocument. Five are Docling's own
exports; JATS is this template's (converter/jats.py). The backend imports this
module to validate a request, so it depends on docling-core only.
"""

import json
from dataclasses import dataclass
from typing import Callable, Dict

from docling_core.types.doc import DoclingDocument

from converter.jats import to_jats


@dataclass(frozen=True)
class OutputFormat:
    name: str
    filename: str
    media_type: str
    description: str
    export: Callable[[DoclingDocument], str]


def _json(doc: DoclingDocument) -> str:
    # Page images are dropped: they are rasters of the input, often megabytes
    # per page, and the structure is what the JSON is for.
    data = doc.export_to_dict()
    for page in (data.get("pages") or {}).values():
        page["image"] = None
    return json.dumps(data, ensure_ascii=False)


FORMATS: Dict[str, OutputFormat] = {
    f.name: f
    for f in (
        OutputFormat("markdown", "document.md", "text/markdown; charset=utf-8",
                     "Markdown with tables", lambda d: d.export_to_markdown()),
        OutputFormat("html", "document.html", "text/html; charset=utf-8",
                     "HTML page", lambda d: d.export_to_html()),
        OutputFormat("text", "document.txt", "text/plain; charset=utf-8",
                     "Plain text", lambda d: d.export_to_text()),
        OutputFormat("json", "document.json", "application/json",
                     "Docling JSON: the full document structure, lossless", _json),
        OutputFormat("doctags", "document.doctags", "text/plain; charset=utf-8",
                     "DocTags markup with page locations", lambda d: d.export_to_doctags()),
        OutputFormat("jats", "document.jats.xml", "application/xml",
                     "JATS XML (Archiving 1.4) for scholarly articles", to_jats),
    )
}

PIPELINES = {
    "standard": "Docling's layout and table models, on CPU in the conversion step",
    "granite-docling": "Granite-Docling through the LLM Gateway, one request per page",
}
