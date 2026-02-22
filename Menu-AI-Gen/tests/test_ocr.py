"""Unit tests for the OCR module."""

import pytest
from unittest.mock import MagicMock

from menu_vision.ocr import extract_text, OCRExtractionError


class TestExtractText:
    """Tests for extract_text()."""

    def test_extracts_lines_from_textract_response(self):
        """Successful extraction concatenates LINE blocks with newlines."""
        mock_client = MagicMock()
        mock_client.detect_document_text.return_value = {
            "Blocks": [
                {"BlockType": "PAGE", "Text": "full page"},
                {"BlockType": "LINE", "Text": "Boeuf Bourguignon"},
                {"BlockType": "LINE", "Text": "€24.50"},
                {"BlockType": "WORD", "Text": "Boeuf"},
            ]
        }

        result = extract_text(b"fake-image-bytes", textract_client=mock_client)

        assert result == "Boeuf Bourguignon\n€24.50"
        mock_client.detect_document_text.assert_called_once_with(
            Document={"Bytes": b"fake-image-bytes"}
        )

    def test_raises_error_when_no_text_detected(self):
        """Raises OCRExtractionError when no LINE blocks are found."""
        mock_client = MagicMock()
        mock_client.detect_document_text.return_value = {
            "Blocks": [
                {"BlockType": "PAGE"},
            ]
        }

        with pytest.raises(OCRExtractionError, match="No text detected"):
            extract_text(b"blank-image", textract_client=mock_client)

    def test_raises_error_when_blocks_empty(self):
        """Raises OCRExtractionError when Blocks list is empty."""
        mock_client = MagicMock()
        mock_client.detect_document_text.return_value = {"Blocks": []}

        with pytest.raises(OCRExtractionError):
            extract_text(b"empty-image", textract_client=mock_client)

    def test_raises_error_when_no_blocks_key(self):
        """Raises OCRExtractionError when response has no Blocks key."""
        mock_client = MagicMock()
        mock_client.detect_document_text.return_value = {}

        with pytest.raises(OCRExtractionError):
            extract_text(b"bad-response", textract_client=mock_client)

    def test_filters_only_line_blocks(self):
        """Only LINE blocks are included, PAGE and WORD blocks are ignored."""
        mock_client = MagicMock()
        mock_client.detect_document_text.return_value = {
            "Blocks": [
                {"BlockType": "PAGE", "Text": "Page text"},
                {"BlockType": "LINE", "Text": "Menu Item 1"},
                {"BlockType": "WORD", "Text": "Menu"},
                {"BlockType": "LINE", "Text": "Menu Item 2"},
                {"BlockType": "WORD", "Text": "Item"},
            ]
        }

        result = extract_text(b"image", textract_client=mock_client)
        assert result == "Menu Item 1\nMenu Item 2"

    def test_single_line_extraction(self):
        """A single LINE block returns just that line without trailing newline."""
        mock_client = MagicMock()
        mock_client.detect_document_text.return_value = {
            "Blocks": [
                {"BlockType": "LINE", "Text": "Solo dish"},
            ]
        }

        result = extract_text(b"image", textract_client=mock_client)
        assert result == "Solo dish"

    def test_textract_api_error_propagates(self):
        """Textract ClientError propagates up to the caller."""
        from botocore.exceptions import ClientError

        mock_client = MagicMock()
        mock_client.detect_document_text.side_effect = ClientError(
            {"Error": {"Code": "InvalidParameterException", "Message": "Bad image"}},
            "DetectDocumentText",
        )

        with pytest.raises(ClientError):
            extract_text(b"corrupt-image", textract_client=mock_client)

