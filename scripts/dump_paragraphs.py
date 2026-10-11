"""Dump paragraph flags (has_image/has_table/has_formula/text) for the sample docx."""

from pathlib import Path
from papergroom.parser import parse_document

doc = parse_document("论文.docx")
print(f"source: {doc.source_path}")
print(f"paragraphs: {len(doc.paragraphs)}")
print("-" * 80)
for p in doc.paragraphs:
    flags = []
    if p.has_image:
        flags.append("IMG")
    if p.has_table:
        flags.append("TBL")
    if p.has_formula:
        flags.append("FML")
    flag_str = ",".join(flags) or "-"
    text = p.text[:60] if p.text else "(empty)"
    print(f"  [{p.index:>2}] flags={flag_str:<12} style={str(p.style_hint):<15} text={text}")
