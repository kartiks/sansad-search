"""Tests for ingest.parsers.pdf_parser — embedded-text only, no OCR."""
import io
import pytest

import fitz  # PyMuPDF

from ingest.parsers.pdf_parser import parse_pdf


def _make_blank_pdf() -> bytes:
    """Create a PDF with one blank page (no embedded text)."""
    doc = fitz.open()
    doc.new_page()
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


_PAD = "Parliamentary proceedings content to meet minimum text threshold."


def _make_pdf(pages: list[str]) -> bytes:
    """Create a minimal in-memory PDF with given text on each page.

    Each page's text is supplemented with _PAD so it reliably exceeds
    the _MIN_EMBEDDED_CHARS threshold in the embedded-text extraction path.
    """
    doc = fitz.open()
    for text in pages:
        page = doc.new_page()
        page.insert_text((72, 72), text + "\n" + _PAD, fontsize=12)
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


class TestParsePdf:
    def test_invalid_source_raises(self):
        pdf = _make_pdf(["test"])
        with pytest.raises(ValueError, match="Invalid source"):
            parse_pdf(pdf, "XX")

    def test_returns_correct_source_ca(self):
        pdf = _make_pdf(["Constituent Assembly Debates\n1 December 1946"])
        result = parse_pdf(pdf, "CA", volume=1)
        assert result is not None
        assert result["source"] == "CA"

    def test_returns_correct_source_ls(self):
        pdf = _make_pdf(["Lok Sabha Debates\n15 March 2023"])
        result = parse_pdf(pdf, "LS")
        assert result is not None
        assert result["source"] == "LS"

    def test_volume_preserved(self):
        pdf = _make_pdf(["CA Volume 7"])
        result = parse_pdf(pdf, "CA", volume=7)
        assert result is not None
        assert result["volume"] == 7

    def test_volume_none_for_ls(self):
        pdf = _make_pdf(["LS Debate"])
        result = parse_pdf(pdf, "LS")
        assert result is not None
        assert result["volume"] is None

    def test_source_url_preserved(self):
        pdf = _make_pdf(["text"])
        url = "https://sansad.in/ca/vol1.pdf"
        result = parse_pdf(pdf, "CA", source_url=url)
        assert result is not None
        assert result["source_url"] == url

    def test_extracts_text_from_digital_page(self):
        speech = "SHRI JAWAHARLAL NEHRU : I rise to move the resolution."
        pdf = _make_pdf([speech])
        result = parse_pdf(pdf, "CA")
        assert result is not None
        assert "NEHRU" in result["raw_text"]

    def test_no_ocr_low_confidence_field(self):
        """ocr_low_confidence has been dropped from the schema; must not appear."""
        pdf = _make_pdf(["This is a digital page with plenty of embedded text content here."])
        result = parse_pdf(pdf, "CA")
        assert result is not None
        assert "ocr_low_confidence" not in result

    def test_pages_list_has_correct_length(self):
        pdf = _make_pdf(["Page one content", "Page two content", "Page three content"])
        result = parse_pdf(pdf, "CA")
        assert result is not None
        assert len(result["pages"]) == 3

    def test_pages_have_page_num_1_based(self):
        pdf = _make_pdf(["page a", "page b"])
        result = parse_pdf(pdf, "CA")
        assert result is not None
        assert result["pages"][0]["page_num"] == 1
        assert result["pages"][1]["page_num"] == 2

    def test_no_ocr_fields_in_page_entries(self):
        """Page entries must not contain 'ocr' or 'ocr_confidence' fields."""
        pdf = _make_pdf(["Sufficient embedded text on this page for extraction."])
        result = parse_pdf(pdf, "CA")
        assert result is not None
        page = result["pages"][0]
        assert "ocr" not in page
        assert "ocr_confidence" not in page

    def test_proceeding_type_hint_applied(self):
        pdf = _make_pdf(["starred question content"])
        result = parse_pdf(pdf, "LS", proceeding_type_hint="starred_question")
        assert result is not None
        assert result["proceeding_type"] == "starred_question"

    def test_date_extracted_from_first_page(self):
        pdf = _make_pdf(["Constituent Assembly Debates\n1st December 1946\nSome content"])
        result = parse_pdf(pdf, "CA")
        assert result is not None
        assert result["date"] == "1946-12-01"

    def test_raw_text_joins_all_pages(self):
        pdf = _make_pdf(["First page text here.", "Second page text here."])
        result = parse_pdf(pdf, "CA")
        assert result is not None
        assert "First page" in result["raw_text"]
        assert "Second page" in result["raw_text"]

    def test_accepts_bytes_input(self):
        pdf = _make_pdf(["bytes input test"])
        result = parse_pdf(pdf, "LS")
        assert isinstance(result, dict)
        assert result["source"] == "LS"

    def test_page_reference_is_one(self):
        pdf = _make_pdf(["content"])
        result = parse_pdf(pdf, "CA")
        assert result is not None
        assert result["page_reference"] == 1

    def test_textless_pdf_returns_none(self):
        """A PDF with no embedded text must return None (logged + skipped)."""
        pdf = _make_blank_pdf()
        result = parse_pdf(pdf, "CA")
        assert result is None, (
            "parse_pdf must return None for a text-less PDF — no OCR fallback in Phase 7+"
        )

    def test_textless_pdf_no_ocr_triggered(self):
        """Confirm no OCR is attempted for text-less PDFs (pytesseract is not imported)."""
        import sys
        pdf = _make_blank_pdf()
        # pytesseract should not be importable (removed from requirements)
        # Even if it were present, pdf_parser must not call it
        result = parse_pdf(pdf, "LS")
        assert result is None
        # pytesseract must not be referenced anywhere in the parse_pdf code path
        import ingest.parsers.pdf_parser as pdf_module
        import inspect
        src = inspect.getsource(pdf_module)
        assert "pytesseract" not in src, (
            "pytesseract must not appear in pdf_parser source after Phase 7 OCR removal"
        )
        assert "tesseract" not in src.lower(), (
            "Any tesseract reference must be absent from pdf_parser after Phase 7"
        )
