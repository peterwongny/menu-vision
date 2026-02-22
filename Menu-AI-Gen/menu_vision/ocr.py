"""OCR module - extracts text from menu images using Amazon Textract."""

import boto3


class OCRExtractionError(Exception):
    """Raised when no text is detected in the image."""


def extract_text(image_bytes: bytes, textract_client=None) -> str:
    """
    Calls Amazon Textract to extract text from image bytes.
    Returns raw extracted text as a single string.
    Raises: OCRExtractionError if no text detected.
    """
    if textract_client is None:
        textract_client = boto3.client("textract")

    response = textract_client.detect_document_text(
        Document={"Bytes": image_bytes}
    )

    lines = [
        block["Text"]
        for block in response.get("Blocks", [])
        if block.get("BlockType") == "LINE" and "Text" in block
    ]

    if not lines:
        raise OCRExtractionError("No text detected in the uploaded image")

    return "\n".join(lines)
