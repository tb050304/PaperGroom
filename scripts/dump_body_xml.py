"""Dump the raw block-level children of the document body element.

This walks the actual <w:body> children in order, so we can see what's
really there (paragraphs, tables, sectPr, etc.) — not just what
python-docx chooses to expose via .paragraphs.
"""

from __future__ import annotations

import sys
from pathlib import Path

from docx import Document as DocxDocument
from lxml import etree

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"


def main(path: str) -> None:
    doc = DocxDocument(path)
    body = doc.element.body
    if body is None:
        print("no body!")
        return

    children = list(body)
    print(f"body has {len(children)} top-level children")
    print("-" * 80)

    para_idx = 0
    table_idx = 0
    for i, child in enumerate(children):
        tag = etree.QName(child).localname

        if tag == "p":
            text = etree.tostring(child, method="text", encoding="unicode").strip()
            has_drawing = child.find(f".//{{{W_NS}}}drawing") is not None
            has_math = child.find(f".//{{{M_NS}}}oMath") is not None
            has_break = child.find(f".//{{{W_NS}}}br[@{{{W_NS}}}type='page']") is not None
            has_sectPr = child.find(f".//{{{W_NS}}}sectPr") is not None
            flags = []
            if has_drawing:
                flags.append("IMG")
            if has_math:
                flags.append("FML")
            if has_break:
                flags.append("PAGE_BREAK")
            if has_sectPr:
                flags.append("SECT")
            flag_str = ",".join(flags) or "-"
            preview = text[:60] if text else "(empty)"
            print(
                f"  body[{i:>2}] <p>      para_idx={para_idx:>2} flags={flag_str:<18} {preview}"
            )
            para_idx += 1

        elif tag == "tbl":
            # count rows and cells
            rows = child.findall(f"{{{W_NS}}}tr")
            n_rows = len(rows)
            n_cells = sum(
                len(row.findall(f"{{{W_NS}}}tc")) for row in rows
            )
            # grab text of first cell
            first_text = ""
            if rows:
                tc = rows[0].find(f"{{{W_NS}}}tc")
                if tc is not None:
                    first_text = "".join(tc.itertext()).strip()[:40]
            print(
                f"  body[{i:>2}] <tbl>    table_idx={table_idx} rows={n_rows} cells={n_cells} first_cell={first_text!r}"
            )
            table_idx += 1

        elif tag == "sectPr":
            print(f"  body[{i:>2}] <sectPr> (final section properties)")

        else:
            print(f"  body[{i:>2}] <{tag}>")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: python scripts/dump_body_xml.py <file.docx>")
    main(sys.argv[1])
