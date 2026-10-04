# Copyright Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: MIT

"""JATS XML from a DoclingDocument.

Docling reads JATS but does not write it. This module maps the structure
Docling recovers from a PDF onto the JATS Archiving and Interchange tag set,
version 1.4, and the result validates against that schema.

What a PDF gives and what it does not:

* Title, headings, paragraphs, lists, tables, figure captions, formulas,
  footnotes and the reference list are labelled by Docling's models, and each
  becomes its JATS element.
* Authors, affiliations, journal, dates and identifiers are running text on
  the first page, not labelled items. They are kept in
  <front>/<notes notes-type="front-matter">, so they are not lost and not
  mistaken for article metadata. When the document has an Abstract heading,
  everything before it is front matter, headings included (publisher banners
  such as "OPEN ACCESS" are headings to Docling); otherwise everything before
  the first heading is.
* A reference is one string. It becomes <mixed-citation> with no inner
  structure.

Section rules, by heading text:

* "Abstract" starts <abstract>. When a heading comes right after it, the
  abstract is structured: the headings that follow stay inside it while they
  are structured-abstract section names (Background, Methods, Results, ...)
  not already used in it. An abstract that starts with a paragraph ends at
  the next heading.
* "References", "Bibliography" and similar start <ref-list> in <back>.
* "Acknowledgments" starts <ack> in <back>.
* Declarations that belong after the article (author contributions,
  funding, competing interests, data availability, supporting information)
  become <sec> in <back>.
* Every other heading opens a <sec> in <body>, nested by heading level.
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional

from docling_core.types.doc import (
    DocItemLabel,
    DoclingDocument,
    FormulaItem,
    GroupItem,
    GroupLabel,
    ListItem,
    NodeItem,
    PictureItem,
    SectionHeaderItem,
    TableItem,
    TextItem,
    TitleItem,
)
from lxml import etree

XLINK_NS = "http://www.w3.org/1999/xlink"
MML_NS = "http://www.w3.org/1998/Math/MathML"
DTD_VERSION = "1.4"

ABSTRACT_HEADINGS = {"abstract", "summary"}
ABSTRACT_SECTION_HEADINGS = {
    "background", "introduction", "context", "purpose", "aim", "aims",
    "objective", "objectives", "design", "setting", "settings", "participants",
    "patients", "interventions", "method", "methods", "materials and methods",
    "methods and findings", "measurements", "main outcome measures", "results",
    "findings", "interpretation", "discussion", "conclusion", "conclusions",
    "limitations", "trial registration", "registration", "funding",
}
REFERENCE_HEADINGS = {
    "references", "reference", "bibliography", "literature cited",
    "works cited", "references cited",
}
ACK_HEADINGS = {"acknowledgments", "acknowledgements", "acknowledgment", "acknowledgement"}
BACK_HEADINGS = {
    "author contributions", "authors' contributions", "author contribution",
    "funding", "competing interests", "conflict of interest",
    "conflicts of interest", "declaration of competing interest",
    "data availability", "data availability statement",
    "supporting information", "supplementary material",
    "supplementary materials", "abbreviations", "ethics statement",
}


def _norm(text: str) -> str:
    """Heading text in the form the rules compare: lower case, no numbering or trailing colon."""
    text = re.sub(r"^\s*(\d+(\.\d+)*\.?|[IVXLC]+\.)\s+", "", text or "")
    return re.sub(r"\s+", " ", text).strip().rstrip(":.").lower()


def _sub(parent: etree._Element, tag: str, text: Optional[str] = None, **attrs) -> etree._Element:
    el = etree.SubElement(parent, tag, {k.replace("_", "-"): v for k, v in attrs.items()})
    if text is not None:
        el.text = _clean(text)
    return el


_XML_ILLEGAL = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]")


def _clean(text: str) -> str:
    """Text with the characters XML 1.0 forbids removed."""
    return _XML_ILLEGAL.sub("", text)


@dataclass
class _Ids:
    counters: dict = field(default_factory=dict)

    def next(self, prefix: str) -> str:
        self.counters[prefix] = self.counters.get(prefix, 0) + 1
        return f"{prefix}{self.counters[prefix]}"


class _Writer:
    """Walks the document body once and fills the article skeleton."""

    def __init__(self, doc: DoclingDocument, has_abstract: bool):
        self.doc = doc
        self.has_abstract = has_abstract
        self.ids = _Ids()
        nsmap = {"xlink": XLINK_NS, "mml": MML_NS}
        self.article = etree.Element(
            "article",
            {"article-type": "research-article", "dtd-version": DTD_VERSION},
            nsmap=nsmap,
        )
        front = _sub(self.article, "front")
        self.article_meta = _sub(front, "article-meta")
        self.front = front
        self.body = _sub(self.article, "body")
        self.back = _sub(self.article, "back")

        self.title_done = False
        self.front_notes: Optional[etree._Element] = None
        self.front_container: Optional[etree._Element] = None
        self.abstract: Optional[etree._Element] = None
        self.abstract_level = 0
        self.abstract_seen: set = set()
        self.ack: Optional[etree._Element] = None
        self.fn_group: Optional[etree._Element] = None
        self.ref_list: Optional[etree._Element] = None

        # The element that receives block content, and the section stack
        # [(level, element)] it belongs to.
        self.container: Optional[etree._Element] = None
        self.stack: List[tuple] = []
        self.mode = "front"

    # --- sections -------------------------------------------------------

    def heading(self, item: SectionHeaderItem):
        name = _norm(item.text)
        level = max(int(getattr(item, "level", 1) or 1), 1)

        if self.mode == "front" and self.has_abstract and name not in ABSTRACT_HEADINGS:
            if self.front_notes is None:
                self.front_notes = _sub(self.front, "notes", notes_type="front-matter")
            sec = _sub(self.front_notes, "sec")
            _sub(sec, "title", item.text)
            self.front_container = sec
            return

        structured = self.abstract is not None and self.abstract.find("p") is None
        if self.mode == "abstract" and structured and level <= self.abstract_level + 1 and (
            name in ABSTRACT_SECTION_HEADINGS and name not in self.abstract_seen
        ):
            self.abstract_seen.add(name)
            sec = _sub(self.abstract, "sec")
            _sub(sec, "title", item.text)
            self.container = sec
            return

        if name in ABSTRACT_HEADINGS and self.abstract is None:
            self.abstract = _sub(self.article_meta, "abstract")
            self.abstract_level = level
            self.mode = "abstract"
            self.container = self.abstract
            return

        if name in REFERENCE_HEADINGS:
            self.ref_list = _sub(self.back, "ref-list")
            _sub(self.ref_list, "title", item.text)
            self.mode = "references"
            self.container = None
            return

        if name in ACK_HEADINGS:
            self.ack = _sub(self.back, "ack")
            _sub(self.ack, "title", item.text)
            self.mode = "back"
            self.container = self.ack
            return

        if name in BACK_HEADINGS:
            sec = _sub(self.back, "sec")
            _sub(sec, "title", item.text)
            self.mode = "back"
            self.container = sec
            return

        self.mode = "body"
        while self.stack and self.stack[-1][0] >= level:
            self.stack.pop()
        parent = self.stack[-1][1] if self.stack else self.body
        sec = _sub(parent, "sec", id=self.ids.next("sec"))
        _sub(sec, "title", item.text)
        self.stack.append((level, sec))
        self.container = sec

    # --- blocks ---------------------------------------------------------

    def target(self) -> etree._Element:
        """Where a block goes in the current mode."""
        if self.mode == "front":
            if self.front_container is not None:
                return self.front_container
            if self.front_notes is None:
                self.front_notes = _sub(self.front, "notes", notes_type="front-matter")
            return self.front_notes
        if self.mode == "references":
            # A table, figure or formula under the reference heading ends the
            # reference list: JATS allows no block after the references.
            sec = _sub(self.back, "sec")
            self.mode, self.container = "back", sec
            return sec
        if self.container is None:
            self.container = self.body
        return self.container

    def paragraph(self, text: str):
        if not text or not text.strip():
            return
        if self.mode == "references":
            self.reference(text)
            return
        _sub(self.target(), "p", text)

    def reference(self, text: str):
        ref = _sub(self.ref_list, "ref", id=self.ids.next("ref"))
        _sub(ref, "mixed-citation", re.sub(r"^\s*\[?\d+\]?\.?\s+", "", text))

    def title(self, item: TitleItem):
        if self.title_done:
            self.paragraph(item.text)
            return
        group = _sub(self.article_meta, "title-group")
        _sub(group, "article-title", item.text)
        # title-group comes first in article-meta.
        self.article_meta.remove(group)
        self.article_meta.insert(0, group)
        self.title_done = True

    def footnote(self, text: str):
        if self.fn_group is None:
            self.fn_group = _sub(self.back, "fn-group")
        fn = _sub(self.fn_group, "fn", id=self.ids.next("fn"))
        _sub(fn, "p", text)

    def formula(self, item: FormulaItem):
        text = item.text or item.orig
        if not text:
            return
        formula = _sub(self.target(), "disp-formula", id=self.ids.next("eq"))
        tex = _sub(formula, "tex-math")
        tex.text = etree.CDATA(_clean(text))

    def code(self, item: TextItem):
        if item.text:
            _sub(self.target(), "code", item.text)

    def captions(self, parent: etree._Element, item) -> bool:
        texts = [ref.resolve(self.doc).text for ref in item.captions]
        texts = [t for t in texts if t and t.strip()]
        if not texts:
            return False
        caption = _sub(parent, "caption")
        for text in texts:
            _sub(caption, "p", text)
        return True

    def figure(self, item):
        if not item.captions:
            return
        fig = etree.Element("fig", id=self.ids.next("fig"))
        if self.captions(fig, item):
            self.target().append(fig)

    def table(self, item: TableItem):
        grid = item.data.table_cells
        if not grid:
            # A region detected as a table whose cells were not recovered is,
            # in the output, only its caption: written as a figure would be.
            self.figure(item)
            return
        wrap = _sub(self.target(), "table-wrap", id=self.ids.next("table"))
        self.captions(wrap, item)
        table = _sub(wrap, "table")
        header_rows = {c.start_row_offset_idx for c in grid if c.column_header}
        rows: dict = {}
        for cell in grid:
            rows.setdefault(cell.start_row_offset_idx, []).append(cell)
        head = body = None
        for row_index in sorted(rows):
            in_head = row_index in header_rows and (body is None)
            if in_head:
                head = head if head is not None else _sub(table, "thead")
                section = head
            else:
                body = body if body is not None else _sub(table, "tbody")
                section = body
            tr = _sub(section, "tr")
            for cell in sorted(rows[row_index], key=lambda c: c.start_col_offset_idx):
                attrs = {}
                if cell.row_span > 1:
                    attrs["rowspan"] = str(cell.row_span)
                if cell.col_span > 1:
                    attrs["colspan"] = str(cell.col_span)
                _sub(tr, "th" if (in_head or cell.row_header) else "td", cell.text or "", **attrs)
        if head is not None and body is None:
            # A table of header cells only still needs a body in JATS.
            _sub(table, "tbody")

    def list_group(self, group: GroupItem):
        items = [child.resolve(self.doc) for child in group.children]
        if self.mode == "references":
            for item in items:
                text = self.text_of(item)
                if text:
                    self.reference(text)
            return
        ordered = group.label == GroupLabel.ORDERED_LIST or any(
            isinstance(i, ListItem) and i.enumerated for i in items
        )
        lst = _sub(self.target(), "list", list_type="order" if ordered else "bullet")
        for item in items:
            if isinstance(item, GroupItem) and item.label in (GroupLabel.LIST, GroupLabel.ORDERED_LIST):
                # A nested list belongs to the list item before it.
                last = lst[-1] if len(lst) else _sub(lst, "list-item")
                saved = self.container, self.mode
                self.container, self.mode = last, "body"
                self.list_group(item)
                self.container, self.mode = saved
                continue
            text = self.text_of(item)
            if text:
                li = _sub(lst, "list-item")
                _sub(li, "p", text)

    def text_of(self, item: NodeItem) -> str:
        """The text of an item, or of an inline group's children joined."""
        if isinstance(item, TextItem):
            return item.text or ""
        if isinstance(item, GroupItem):
            return " ".join(t for t in (self.text_of(c.resolve(self.doc)) for c in item.children) if t)
        return ""

    # --- walk -----------------------------------------------------------

    def walk(self, node: NodeItem):
        for ref in node.children:
            item = ref.resolve(self.doc)
            self.visit(item)

    def visit(self, item: NodeItem):
        if isinstance(item, GroupItem):
            if item.label in (GroupLabel.LIST, GroupLabel.ORDERED_LIST):
                self.list_group(item)
            elif item.label == GroupLabel.INLINE:
                self.paragraph(self.text_of(item))
            else:
                self.walk(item)
            return
        if isinstance(item, TitleItem):
            self.title(item)
        elif isinstance(item, SectionHeaderItem):
            self.heading(item)
        elif isinstance(item, TableItem):
            self.table(item)
        elif isinstance(item, PictureItem):
            self.figure(item)
        elif isinstance(item, FormulaItem):
            self.formula(item)
        elif isinstance(item, ListItem):
            if self.mode == "references":
                self.reference(item.text)
            else:
                lst = _sub(self.target(), "list", list_type="order" if item.enumerated else "bullet")
                li = _sub(lst, "list-item")
                _sub(li, "p", item.text)
        elif isinstance(item, TextItem):
            if item.label == DocItemLabel.CAPTION:
                # Captions attached to a table or picture are written with it.
                if not self._is_attached_caption(item):
                    self.paragraph(item.text)
            elif item.label == DocItemLabel.FOOTNOTE:
                self.footnote(item.text)
            elif item.label == DocItemLabel.CODE:
                self.code(item)
            elif item.label in (DocItemLabel.PAGE_HEADER, DocItemLabel.PAGE_FOOTER):
                return
            else:
                self.paragraph(item.text)
        # Key-value regions, forms and other item kinds have no JATS equivalent here.

    def _is_attached_caption(self, item: TextItem) -> bool:
        return isinstance(item.parent.resolve(self.doc), (TableItem, PictureItem)) if item.parent else False

    def finish(self) -> etree._Element:
        # Empty containers are not valid in every position; drop the ones nothing reached.
        for el in (self.body, self.back):
            if len(el) == 0:
                self.article.remove(el)
        if self.abstract is not None and len(self.abstract) == 0:
            self.article_meta.remove(self.abstract)
        if self.ref_list is not None and len(self.ref_list.findall("ref")) == 0:
            # A reference heading with nothing under it keeps its title only as a section.
            parent = self.ref_list.getparent()
            parent.remove(self.ref_list)
            if len(parent) == 0 and parent is self.back:
                self.article.remove(self.back)
        return self.article


def to_jats(doc: DoclingDocument) -> str:
    """The document as a JATS 1.4 article, serialized with an XML declaration."""
    has_abstract = any(
        isinstance(item, SectionHeaderItem) and _norm(item.text) in ABSTRACT_HEADINGS
        for item, _ in doc.iterate_items()
    )
    writer = _Writer(doc, has_abstract)
    writer.walk(doc.body)
    article = writer.finish()
    return etree.tostring(article, xml_declaration=True, encoding="UTF-8", pretty_print=True).decode("utf-8")

