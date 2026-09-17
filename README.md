# tkt-docling

A Thinkube template that converts PDFs, such as scientific and medical papers, into structured text with [Docling](https://github.com/docling-project/docling).

Deploy it from thinkube-control under **Templates**, or ask Claude Code: *"deploy the docling template, call it docling"*.

## What it does

Upload a PDF, choose a pipeline and the output formats, and download the results from the web page or through the REST API.

| Format | File | What it is |
|---|---|---|
| `markdown` | `document.md` | Markdown with tables |
| `html` | `document.html` | HTML page |
| `text` | `document.txt` | Plain text |
| `json` | `document.json` | Docling JSON: the whole document structure |
| `doctags` | `document.doctags` | DocTags markup with page locations |
| `jats` | `document.jats.xml` | JATS XML, Archiving and Interchange 1.4 |

| Pipeline | Where it runs |
|---|---|
| `standard` | Docling's layout and table models, on CPU in the conversion step. The first standard conversion downloads the models once into Thinkube Storage. |
| `granite-docling` | [Granite-Docling 258M](https://huggingface.co/ibm-granite/granite-docling-258M) through the LLM Gateway, one request per page. |

## How it fits together

- **Web app template.** React on thinkube-style, FastAPI, PostgreSQL, sign-in through Thinkube Identity, API tokens.
- **Argo Workflows** (`services: [workflows]`). Each conversion is one workflow step that runs `python -m converter.run` in the backend's own image.
- **Thinkube Storage.** The PDF and the outputs are artifacts under `argo-artifacts/<app>/conversions/<id>/`, and the Docling models under `argo-artifacts/<app>/docling-models/<version>/`. The step reads and writes them by key.
- **LLM Gateway** (`dependencies: llm-proxy`). The granite-docling step calls the gateway with `THINKUBE_API_TOKEN` from the app's secrets.

## Before you deploy

- For `granite-docling`: load `ibm-granite/granite-docling-258M` on the LLM Gateway, and add a thinkube-control API token as `THINKUBE_API_TOKEN` on the Secrets page. Without the token, the page offers only `standard`.

## API

All routes are under `/api/v1/conversions` and take a Thinkube Identity token or an API token from this app's **API Tokens** page.

```bash
curl -H "Authorization: Bearer $TOKEN" \
  -F file=@paper.pdf -F pipeline=standard -F formats=markdown,jats \
  https://<app>.<domain>/api/v1/conversions

curl -H "Authorization: Bearer $TOKEN" https://<app>.<domain>/api/v1/conversions/<id>
curl -H "Authorization: Bearer $TOKEN" -o paper.jats.xml \
  https://<app>.<domain>/api/v1/conversions/<id>/outputs/jats
```

The OpenAPI page is at `/api/v1/docs`.

## JATS output

`backend/converter/jats.py` maps Docling's document onto JATS. Title, abstract, sections, paragraphs, lists, tables, figure captions, formulas (as `tex-math`), footnotes, acknowledgments and the reference list get their JATS elements. The tests validate the output against the JATS 1.4 schema (`backend/tests/schemas`).

Limits of what a PDF gives:

- Authors, affiliations, journal and dates are plain text on the first page. They are kept in `<front>/<notes notes-type="front-matter">`, not split into metadata fields.
- Each reference is one `<mixed-citation>` string.
- Text is placed in Docling's reading order. A first-page sidebar can appear inside the abstract.
- Figures carry their captions only; the images are not exported.

## License

Apache 2.0. Docling and Granite-Docling are MIT and Apache 2.0. The JATS schema under `backend/tests/schemas` is published by the U.S. National Library of Medicine and is in the public domain.
