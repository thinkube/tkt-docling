# Copyright Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: MIT

"""JATS output: valid against JATS Archiving 1.4, and each mapping rule holds.

The two fixtures are the same open-access paper (PLOS ONE,
doi:10.1371/journal.pone.0297349, CC BY 4.0) converted by the standard
pipeline and by Granite-Docling. The schema is the NLM JATS Archiving and
Interchange 1.4 XSD with MathML 3, kept under tests/schemas.
"""

from pathlib import Path

import pytest
from docling_core.types.doc import (
    DocItemLabel,
    DoclingDocument,
    GroupLabel,
    TableCell,
    TableData,
)
from lxml import etree

from converter.jats import to_jats

HERE = Path(__file__).parent
SCHEMA_PATH = HERE / "schemas" / "jats-archiving-1.4" / "JATS-archivearticle1-4-mathml3.xsd"


@pytest.fixture(scope="module")
def schema():
    return etree.XMLSchema(etree.parse(str(SCHEMA_PATH)))


def parse(xml: str) -> etree._Element:
    return etree.fromstring(xml.encode("utf-8"))


def assert_valid(schema, xml: str):
    tree = parse(xml)
    if not schema.validate(tree):
        errors = "\n".join(str(e) for e in schema.error_log)
        pytest.fail(f"JATS output is not valid:\n{errors}")
    return tree


@pytest.mark.parametrize("fixture", ["pone.0297349.standard.json", "pone.0297349.granite-docling.json"])
def test_paper_is_valid_jats(schema, fixture):
    doc = DoclingDocument.load_from_json(HERE / "fixtures" / fixture)
    tree = assert_valid(schema, to_jats(doc))

    assert tree.get("dtd-version") == "1.4"
    sec_titles = [t.text for t in tree.findall("body/sec/title")]
    assert "Materials and methods" in sec_titles
    assert "Discussion" in sec_titles

    abstract_titles = [t.text for t in tree.findall("front/article-meta/abstract/sec/title")]
    assert abstract_titles[:2] == ["Background", "Methods"]

    refs = tree.findall("back/ref-list/ref/mixed-citation")
    assert len(refs) >= 20
    assert refs[0].text.startswith("Cooper KL")

    assert tree.find("back/ack/p") is not None

    front_titles = [t.text for t in tree.findall("front/notes/sec/title")]
    assert front_titles == ["OPEN ACCESS" if "granite" in fixture else "OPENACCESS"]
    assert "OPEN ACCESS" not in sec_titles and "OPENACCESS" not in sec_titles


def test_title_goes_to_article_meta(schema):
    doc = DoclingDocument(name="t")
    doc.add_title("A trial of two fixations")
    doc.add_heading("Introduction", level=1)
    doc.add_text(DocItemLabel.TEXT, "Body text.")
    tree = assert_valid(schema, to_jats(doc))

    assert tree.findtext("front/article-meta/title-group/article-title") == "A trial of two fixations"
    assert tree.findtext("body/sec/p") == "Body text."


def test_text_before_first_heading_is_front_matter(schema):
    doc = DoclingDocument(name="t")
    doc.add_text(DocItemLabel.TEXT, "Received: July 27, 2023")
    doc.add_heading("Introduction", level=1)
    doc.add_text(DocItemLabel.TEXT, "Body.")
    tree = assert_valid(schema, to_jats(doc))

    notes = tree.find("front/notes")
    assert notes.get("notes-type") == "front-matter"
    assert notes.findtext("p") == "Received: July 27, 2023"


def test_structured_abstract_ends_at_repeated_heading(schema):
    doc = DoclingDocument(name="t")
    doc.add_heading("Abstract", level=1)
    doc.add_heading("Background", level=1)
    doc.add_text(DocItemLabel.TEXT, "Why.")
    doc.add_heading("Results", level=1)
    doc.add_text(DocItemLabel.TEXT, "What.")
    doc.add_heading("Background", level=1)
    doc.add_text(DocItemLabel.TEXT, "The article's own background.")
    tree = assert_valid(schema, to_jats(doc))

    assert [t.text for t in tree.findall("front/article-meta/abstract/sec/title")] == ["Background", "Results"]
    assert tree.findtext("body/sec/title") == "Background"
    assert tree.findtext("body/sec/p") == "The article's own background."


def test_plain_abstract_paragraphs(schema):
    doc = DoclingDocument(name="t")
    doc.add_heading("Abstract", level=1)
    doc.add_text(DocItemLabel.TEXT, "One paragraph abstract.")
    doc.add_heading("Introduction", level=1)
    tree = assert_valid(schema, to_jats(doc))

    assert tree.findtext("front/article-meta/abstract/p") == "One paragraph abstract."
    assert tree.find("front/article-meta/abstract/sec") is None
    assert tree.findtext("body/sec/title") == "Introduction"


def test_headings_nest_by_level(schema):
    doc = DoclingDocument(name="t")
    doc.add_heading("Methods", level=1)
    doc.add_heading("Design", level=2)
    doc.add_text(DocItemLabel.TEXT, "Cluster cross-over.")
    doc.add_heading("Results", level=1)
    tree = assert_valid(schema, to_jats(doc))

    assert tree.findtext("body/sec[1]/sec/title") == "Design"
    assert tree.findtext("body/sec[2]/title") == "Results"


def test_references_become_mixed_citations(schema):
    doc = DoclingDocument(name="t")
    doc.add_heading("Introduction", level=1)
    doc.add_heading("References", level=1)
    refs = doc.add_group(label=GroupLabel.LIST)
    doc.add_list_item("1. Cooper KL. Evidence-based prevention.", parent=refs, enumerated=True)
    doc.add_list_item("Hemming K, Taljaard M. Sample size.", parent=refs)
    tree = assert_valid(schema, to_jats(doc))

    citations = [c.text for c in tree.findall("back/ref-list/ref/mixed-citation")]
    assert citations == ["Cooper KL. Evidence-based prevention.", "Hemming K, Taljaard M. Sample size."]
    assert [r.get("id") for r in tree.findall("back/ref-list/ref")] == ["ref1", "ref2"]


def test_back_matter_sections(schema):
    doc = DoclingDocument(name="t")
    doc.add_heading("Introduction", level=1)
    doc.add_heading("Acknowledgments", level=1)
    doc.add_text(DocItemLabel.TEXT, "Thanks.")
    doc.add_heading("Author Contributions", level=1)
    doc.add_text(DocItemLabel.TEXT, "Conceptualization: A.")
    tree = assert_valid(schema, to_jats(doc))

    assert tree.findtext("back/ack/p") == "Thanks."
    assert tree.findtext("back/sec/title") == "Author Contributions"


def test_lists(schema):
    doc = DoclingDocument(name="t")
    doc.add_heading("Eligibility", level=1)
    lst = doc.add_group(label=GroupLabel.ORDERED_LIST)
    doc.add_list_item("Adult patient", parent=lst, enumerated=True)
    doc.add_list_item("Intubated", parent=lst, enumerated=True)
    tree = assert_valid(schema, to_jats(doc))

    lst_el = tree.find("body/sec/list")
    assert lst_el.get("list-type") == "order"
    assert [p.text for p in lst_el.findall("list-item/p")] == ["Adult patient", "Intubated"]


def test_table_with_header_and_spans(schema):
    doc = DoclingDocument(name="t")
    doc.add_heading("Results", level=1)
    cells = [
        TableCell(text="Group", start_row_offset_idx=0, end_row_offset_idx=1,
                  start_col_offset_idx=0, end_col_offset_idx=1, column_header=True),
        TableCell(text="Lesions", start_row_offset_idx=0, end_row_offset_idx=1,
                  start_col_offset_idx=1, end_col_offset_idx=3, col_span=2, column_header=True),
        TableCell(text="A", start_row_offset_idx=1, end_row_offset_idx=2,
                  start_col_offset_idx=0, end_col_offset_idx=1),
        TableCell(text="12", start_row_offset_idx=1, end_row_offset_idx=2,
                  start_col_offset_idx=1, end_col_offset_idx=2),
        TableCell(text="3", start_row_offset_idx=1, end_row_offset_idx=2,
                  start_col_offset_idx=2, end_col_offset_idx=3),
    ]
    table = doc.add_table(data=TableData(num_rows=2, num_cols=3, table_cells=cells))
    caption = doc.add_text(DocItemLabel.CAPTION, "Table 1. Lesions by group.", parent=table)
    table.captions.append(caption.get_ref())
    tree = assert_valid(schema, to_jats(doc))

    wrap = tree.find("body/sec/table-wrap")
    assert wrap.findtext("caption/p") == "Table 1. Lesions by group."
    assert wrap.find("table/thead/tr/th[2]").get("colspan") == "2"
    assert [td.text for td in wrap.findall("table/tbody/tr/td")] == ["A", "12", "3"]
    # The caption is written once, inside the table-wrap.
    assert len(tree.findall(".//p")) == 1


def test_formula_is_tex_math(schema):
    doc = DoclingDocument(name="t")
    doc.add_heading("Sample size", level=1)
    doc.add_text(DocItemLabel.FORMULA, r"n = \frac{(z_{\alpha} + z_{\beta})^2}{\delta^2}")
    tree = assert_valid(schema, to_jats(doc))

    assert tree.findtext("body/sec/disp-formula/tex-math") == r"n = \frac{(z_{\alpha} + z_{\beta})^2}{\delta^2}"


def test_footnote_goes_to_fn_group(schema):
    doc = DoclingDocument(name="t")
    doc.add_heading("Introduction", level=1)
    doc.add_text(DocItemLabel.FOOTNOTE, "* corresponding author")
    tree = assert_valid(schema, to_jats(doc))

    assert tree.findtext("back/fn-group/fn/p") == "* corresponding author"


def test_uncaptioned_picture_is_left_out(schema):
    doc = DoclingDocument(name="t")
    doc.add_heading("Introduction", level=1)
    doc.add_picture()
    tree = assert_valid(schema, to_jats(doc))

    assert tree.find(".//fig") is None


def test_table_after_references_ends_the_list(schema):
    doc = DoclingDocument(name="t")
    doc.add_heading("References", level=1)
    doc.add_text(DocItemLabel.TEXT, "Cooper KL. Evidence.")
    doc.add_table(data=TableData(num_rows=1, num_cols=1, table_cells=[
        TableCell(text="x", start_row_offset_idx=0, end_row_offset_idx=1,
                  start_col_offset_idx=0, end_col_offset_idx=1),
    ]))
    tree = assert_valid(schema, to_jats(doc))

    assert tree.findtext("back/ref-list/ref/mixed-citation") == "Cooper KL. Evidence."
    assert tree.find("back/sec/table-wrap") is not None


def test_control_characters_are_removed(schema):
    doc = DoclingDocument(name="t")
    doc.add_heading("Introduction", level=1)
    doc.add_text(DocItemLabel.TEXT, "Broken\x0bglyph")
    tree = assert_valid(schema, to_jats(doc))

    assert tree.findtext("body/sec/p") == "Brokenglyph"


def test_banner_heading_before_abstract_stays_in_front_matter(schema):
    doc = DoclingDocument(name="t")
    doc.add_heading("OPEN ACCESS", level=1)
    doc.add_text(DocItemLabel.TEXT, "Citation: Zinzoni V, et al. (2024)")
    doc.add_heading("Abstract", level=1)
    doc.add_text(DocItemLabel.TEXT, "Summary.")
    doc.add_heading("Introduction", level=1)
    tree = assert_valid(schema, to_jats(doc))

    banner = tree.find("front/notes/sec")
    assert banner.findtext("title") == "OPEN ACCESS"
    assert banner.findtext("p") == "Citation: Zinzoni V, et al. (2024)"
    assert [t.text for t in tree.findall("body/sec/title")] == ["Introduction"]
