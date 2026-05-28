"""Tests for ingest.parsers.pdf_parser"""
import io
import pytest
from unittest.mock import patch

import fitz  # PyMuPDF

from ingest.parsers.pdf_parser import parse_pdf, OCR_CONFIDENCE_THRESHOLD


def _make_blank_pdf() -> bytes:
    """Create a PDF with one blank page (no embedded text) to trigger OCR fallback."""
    doc = fitz.open()
    doc.new_page()
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def _make_pdf(pages: list[str]) -> bytes:
    """Create a minimal in-memory PDF with given text on each page."""
    doc = fitz.open()
    for text in pages:
        page = doc.new_page()
        page.insert_text((72, 72), text, fontsize=12)
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
        assert result["source"] == "CA"

    def test_returns_correct_source_ls(self):
        pdf = _make_pdf(["Lok Sabha Debates\n15 March 2023"])
        result = parse_pdf(pdf, "LS")
        assert result["source"] == "LS"

    def test_volume_preserved(self):
        pdf = _make_pdf(["CA Volume 7"])
        result = parse_pdf(pdf, "CA", volume=7)
        assert result["volume"] == 7

    def test_volume_none_for_ls(self):
        pdf = _make_pdf(["LS Debate"])
        result = parse_pdf(pdf, "LS")
        assert result["volume"] is None

    def test_source_url_preserved(self):
        pdf = _make_pdf(["text"])
        url = "https://sansad.in/ca/vol1.pdf"
        result = parse_pdf(pdf, "CA", source_url=url)
        assert result["source_url"] == url

    def test_extracts_text_from_digital_page(self):
        speech = "SHRI JAWAHARLAL NEHRU : I rise to move the resolution."
        pdf = _make_pdf([speech])
        result = parse_pdf(pdf, "CA")
        assert "NEHRU" in result["raw_text"]

    def test_ocr_low_confidence_false_for_digital_pdf(self):
        pdf = _make_pdf(["This is a digital page with plenty of embedded text content here."])
        result = parse_pdf(pdf, "CA")
        assert result["ocr_low_confidence"] is False

    def test_pages_list_has_correct_length(self):
        pdf = _make_pdf(["Page one content", "Page two content", "Page three content"])
        result = parse_pdf(pdf, "CA")
        assert len(result["pages"]) == 3

    def test_pages_have_page_num_1_based(self):
        pdf = _make_pdf(["page a", "page b"])
        result = parse_pdf(pdf, "CA")
        assert result["pages"][0]["page_num"] == 1
        assert result["pages"][1]["page_num"] == 2

    def test_digital_pages_not_marked_as_ocr(self):
        pdf = _make_pdf(["Sufficient embedded text on this page for extraction."])
        result = parse_pdf(pdf, "CA")
        assert result["pages"][0]["ocr"] is False
        assert result["pages"][0]["ocr_confidence"] is None

    def test_proceeding_type_hint_applied(self):
        pdf = _make_pdf(["starred question content"])
        result = parse_pdf(pdf, "LS", proceeding_type_hint="starred_question")
        assert result["proceeding_type"] == "starred_question"

    def test_date_extracted_from_first_page(self):
        pdf = _make_pdf(["Constituent Assembly Debates\n1st December 1946\nSome content"])
        result = parse_pdf(pdf, "CA")
        assert result["date"] == "1946-12-01"

    def test_raw_text_joins_all_pages(self):
        pdf = _make_pdf(["First page text here.", "Second page text here."])
        result = parse_pdf(pdf, "CA")
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
        assert result["page_reference"] == 1

    def test_ocr_branch_triggered_for_blank_page(self):
        """A page with no embedded text must invoke _ocr_page (OCR fallback)."""
        pdf = _make_blank_pdf()
        with patch("ingest.parsers.pdf_parser._ocr_page", return_value=("OCR extracted text", 75.0)) as mock_ocr:
            result = parse_pdf(pdf, "CA")
        mock_ocr.assert_called_once()
        assert result["pages"][0]["ocr"] is True
        assert "OCR extracted text" in result["raw_text"]

    def test_ocr_low_confidence_true_when_confidence_below_threshold(self):
        """Pages with OCR confidence below OCR_CONFIDENCE_THRESHOLD set ocr_low_confidence=True."""
        pdf = _make_blank_pdf()
        low_conf = OCR_CONFIDENCE_THRESHOLD - 1.0
        with patch("ingest.parsers.pdf_parser._ocr_page", return_value=("faint scanned text", low_conf)):
            result = parse_pdf(pdf, "CA")
        assert result["ocr_low_confidence"] is True
        assert result["pages"][0]["ocr"] is True
        assert result["pages"][0]["ocr_confidence"] == pytest.approx(low_conf)

    def test_ocr_confidence_stored_on_page_entry(self):
        """OCR confidence value is stored in the page dict for scanned pages."""
        pdf = _make_blank_pdf()
        with patch("ingest.parsers.pdf_parser._ocr_page", return_value=("scanned text", 82.5)):
            result = parse_pdf(pdf, "CA")
        assert result["pages"][0]["ocr_confidence"] == pytest.approx(82.5)
