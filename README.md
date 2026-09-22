# tkt-docling

A Thinkube app template that converts PDFs, such as scientific and medical papers, into structured text with [Docling](https://github.com/docling-project/docling).

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

## How it reaches a user

A person deploys it from the Templates page in thinkube-control, part of
[Thinkube](https://github.com/thinkube/thinkube), or asks Claude Code:
*"deploy the docling template, call it docling"*. The deploy creates the
person's own repository from this template, then builds and deploys the app.
It is not installed on its own.

The walkthrough (load Granite-Docling, deploy, convert a paper on the page
and through the API, compare the pipelines, check the JATS output, and the
limits of what a PDF gives) is on the documentation site:
[Convert papers to Markdown and JATS XML](https://github.com/thinkube/thinkube.org/blob/main/modules/ROOT/pages/playbooks/convert-papers-to-markdown-and-jats.adoc).

## How it fits together

- **Web app template.** React on thinkube-style, FastAPI, PostgreSQL, sign-in through Thinkube Identity, API tokens.
- **Argo Workflows** (`services: [workflows]`). Each conversion is one workflow step that runs `python -m converter.run` in the backend's own image.
- **Thinkube Storage.** The PDF and the outputs are artifacts under `argo-artifacts/<app>/conversions/<id>/`, and the Docling models under `argo-artifacts/<app>/docling-models/<version>/`. The step reads and writes them by key.
- **LLM Gateway** (`dependencies: llm-proxy`). The granite-docling step calls the gateway with `THINKUBE_API_TOKEN` from the app's secrets. The model it calls is `GRANITE_DOCLING_MODEL`, by default `ibm-granite/granite-docling-258M`.

## Before you deploy

- For `granite-docling`: load `ibm-granite/granite-docling-258M` on the LLM Gateway, and add a thinkube-control API token as `THINKUBE_API_TOKEN` on the Secrets page. Without the token, the page offers only `standard`.

## API

All routes are under `/api/v1/conversions` and take a Thinkube Identity token or an API token from this app's **API Tokens** page.

| Method | Path | What it does |
|---|---|---|
| GET | `/api/v1/conversions/options` | the formats and pipelines on offer |
| POST | `/api/v1/conversions` | upload a PDF (`file`, `pipeline`, `formats`) and start a conversion |
| GET | `/api/v1/conversions` | list conversions |
| GET | `/api/v1/conversions/<id>` | one conversion and its state |
| GET | `/api/v1/conversions/<id>/outputs/<format>` | download one output |
| DELETE | `/api/v1/conversions/<id>` | delete a conversion and its files |

The OpenAPI page is at `/api/v1/docs`.

## JATS output

`backend/converter/jats.py` maps Docling's document onto JATS. Title, abstract, sections, paragraphs, lists, tables, figure captions, formulas (as `tex-math`), footnotes, acknowledgments and the reference list get their JATS elements. The tests validate the output against the JATS 1.4 schema (`backend/tests/schemas`).

## Working on it

Each container has a `run_tests.sh`. Without arguments it runs the whole
suite, as CI does before every build. With a file argument it runs that one
test file:

```bash
cd backend && ./run_tests.sh tests/test_jats.py
cd frontend && ./run_tests.sh src/pages/__tests__/ConversionsPage.test.tsx
```

Python packages for the conversion step are in
`backend/requirements-converter.txt`; the API's are in
`backend/requirements.txt`.

## License

MIT. Code generated from this template is yours: no attribution required, and you may license the app you build however you choose. See [LICENSE](LICENSE). Docling and Granite-Docling are MIT and Apache 2.0. The JATS schema under `backend/tests/schemas` is published by the U.S. National Library of Medicine and is in the public domain.

Copyright Alejandro Martínez Corriá and the Thinkube contributors
