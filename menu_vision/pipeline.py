"""Pipeline orchestrator - runs the full OCR → LLM → Image Gen pipeline."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Optional

from menu_vision.image_gen import generate_all_dish_images
from menu_vision.llm import LLMProcessingError, structure_menu
from menu_vision.models import DishRecord, JobStatus, MenuResult
from menu_vision.ocr import OCRExtractionError, extract_text

logger = logging.getLogger(__name__)

PLACEHOLDER_IMAGE_URL = "placeholder://no-image"
DEFAULT_TIMEOUT_THRESHOLD = 720  # 80% of Lambda 900s


def run_pipeline(
    image_path: Optional[str] = None,
    *,
    image_bytes: Optional[bytes] = None,
    timeout_threshold: float = DEFAULT_TIMEOUT_THRESHOLD,
    textract_client=None,
    bedrock_client=None,
) -> MenuResult:
    """
    Runs the full pipeline on a local image file or raw image bytes.

    Calls AWS services (Textract, Bedrock) using local AWS credentials.
    Returns a MenuResult with dish images saved to a local output directory.

    Args:
        image_path: Path to a local image file. Ignored if image_bytes is provided.
        image_bytes: Raw image bytes (for Lambda handler use). Takes priority over image_path.
        timeout_threshold: Max elapsed seconds before stopping image gen (default 720).
        textract_client: Optional Textract client for dependency injection.
        bedrock_client: Optional Bedrock client for dependency injection.

    Returns:
        MenuResult with status COMPLETED, PARTIAL, or FAILED.
    """
    job_id = str(uuid.uuid4())
    start_time = time.monotonic()

    # --- Read image bytes ---
    if image_bytes is None:
        if image_path is None:
            return MenuResult(
                job_id=job_id,
                status=JobStatus.FAILED,
                error_message="Either image_path or image_bytes must be provided",
            )
        try:
            with open(image_path, "rb") as f:
                image_bytes = f.read()
        except OSError as e:
            return MenuResult(
                job_id=job_id,
                status=JobStatus.FAILED,
                error_message=f"Failed to read image file: {e}",
            )

    # --- OCR ---
    try:
        raw_text = extract_text(image_bytes, textract_client=textract_client)
    except OCRExtractionError as e:
        logger.error("OCR extraction failed: %s", e)
        return MenuResult(
            job_id=job_id,
            status=JobStatus.FAILED,
            error_message=f"OCR extraction failed: {e}",
        )

    # --- LLM structuring ---
    try:
        dishes = structure_menu(raw_text, bedrock_client=bedrock_client)
    except LLMProcessingError as e:
        logger.error("LLM processing failed: %s", e)
        return MenuResult(
            job_id=job_id,
            status=JobStatus.FAILED,
            error_message=f"LLM processing failed: {e}",
        )

    if not dishes:
        return MenuResult(
            job_id=job_id,
            status=JobStatus.COMPLETED,
            dishes=[],
        )

    # --- Check timeout before image generation ---
    elapsed = time.monotonic() - start_time
    if elapsed >= timeout_threshold:
        logger.warning("Timeout reached before image generation (%.1fs)", elapsed)
        for dish in dishes:
            dish.image_url = PLACEHOLDER_IMAGE_URL
        return MenuResult(
            job_id=job_id,
            status=JobStatus.PARTIAL,
            dishes=dishes,
            error_message="Timeout reached before image generation could start",
        )

    # --- Parallel image generation ---
    image_results = generate_all_dish_images(dishes, bedrock_client=bedrock_client)

    any_failed = False
    for idx, img_bytes in image_results:
        if img_bytes is not None:
            dishes[idx].image_url = f"generated://dish_{idx}.png"
        else:
            dishes[idx].image_url = PLACEHOLDER_IMAGE_URL
            any_failed = True

    # --- Check timeout after image generation ---
    elapsed = time.monotonic() - start_time
    timed_out = elapsed >= timeout_threshold

    if timed_out or any_failed:
        status = JobStatus.PARTIAL
    else:
        status = JobStatus.COMPLETED

    return MenuResult(
        job_id=job_id,
        status=status,
        dishes=dishes,
    )
