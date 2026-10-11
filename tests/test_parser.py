"""Tests for the docx parser.

We build a small docx in-memory with python-docx so the test is
self-contained (no binary fixture to maintain). Each test covers one
parsing behavior.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from docx import Document as DocxDocument
from docx.shared import Pt

from papergroom.models import Role
from papergroom.parser import parse_document


@pytest.fixture()
def sample_docx(tmp_path: Path) -> Path:
    """Build a tiny .docx with a heading, body, image, and formula.

    Returns the path. Deleted automatically when tmp_path goes away.
    """
    doc = DocxDocument()

    doc.add_heading("Chapter 1 Introduction", level=1)
    doc.add_paragraph("This is the first body paragraph with some text.")
    doc.add_paragraph("Second body paragraph.")

    # An empty paragraph + an inline image (we use a 1x1 PNG placeholder).
    img_para = doc.add_paragraph()
    # add_picture on the document creates a new paragraph; to keep it
    # inside the paragraph we just made, add via run.
    # python-docx expects a file-like (with seek), so wrap bytes in BytesIO.
    import io

    png = _make_1x1_png()
    run = img_para.add_run()
    run.add_picture(io.BytesIO(png))

    doc.add_paragraph("Figure 1: Sample figure caption.")

    # Save to a temp path.
    path = tmp_path / "sample.docx"
    doc.save(str(path))
    return path


def _make_1x1_png() -> bytes:
    """Return bytes of a minimal 1x1 transparent PNG."""
    import struct
    import zlib

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)  # 1x1, 8-bit RGBA
    ihdr_chunk = b"IHDR" + ihdr
    ihdr_full = struct.pack(">I", len(ihdr)) + ihdr_chunk + struct.pack(
        ">I", zlib.crc32(ihdr_chunk) & 0xFFFFFFFF
    )
    raw = b"\x00" + b"\x00\x00\x00\x00"  # filter byte + 1 RGBA pixel (transparent)
    comp = zlib.compress(raw)
    idat_chunk = b"IDAT" + comp
    idat_full = struct.pack(">I", len(comp)) + idat_chunk + struct.pack(
        ">I", zlib.crc32(idat_chunk) & 0xFFFFFFFF
    )
    iend_chunk = b"IEND"
    iend_full = struct.pack(">I", 0) + iend_chunk + struct.pack(
        ">I", zlib.crc32(iend_chunk) & 0xFFFFFFFF
    )
    return sig + ihdr_full + idat_full + iend_full


def test_parse_returns_paragraphs(sample_docx: Path):
    doc = parse_document(sample_docx)
    assert len(doc.paragraphs) >= 4
    assert doc.source_path == str(sample_docx.resolve())


def test_parse_captures_text(sample_docx: Path):
    doc = parse_document(sample_docx)
    texts = [p.text for p in doc.paragraphs]
    assert any("Chapter 1" in t for t in texts)
    assert any("first body paragraph" in t for t in texts)


def test_parse_detects_image(sample_docx: Path):
    doc = parse_document(sample_docx)
    assert any(p.has_image for p in doc.paragraphs)


def test_parse_default_role_unknown(sample_docx: Path):
    doc = parse_document(sample_docx)
    for p in doc.paragraphs:
        assert p.role == Role.UNKNOWN
        assert p.confidence == 0.0


def test_parse_rejects_missing_file(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        parse_document(tmp_path / "nonexistent.docx")


def test_parse_rejects_wrong_extension(tmp_path: Path):
    bad = tmp_path / "not_a_doc.txt"
    bad.write_text("hi")
    with pytest.raises(ValueError):
        parse_document(bad)
