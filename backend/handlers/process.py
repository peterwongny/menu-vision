"""Processing Lambda handler - triggered by S3 event, runs the full pipeline."""

from __future__ import annotations

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import boto3
from botocore.config import Config

from backend.image_gen import MAX_WORKERS, _generate_with_retry
from backend.llm import LLMProcessingError, structure_menu, structure_menu_from_image
from backend.models import JobStatus, MenuResult
from backend.ocr import OCRExtractionError, extract_text
from backend.storage import store_image, store_results

logger = logging.getLogger(__name__)

PLACEHOLDER_IMAGE_URL = "placeholder://no-image"
MIN_OCR_LINES = 3  # If Textract returns fewer lines, fall back to Claude vision


def _extract_dishes(image_bytes, textract_client, bedrock_client, timings):
    """Try Textract OCR first; if it fails or returns too little text, fall back to Claude vision."""

    # --- Try Textract OCR ---
    try:
        t0 = time.time()
        raw_text = extract_text(image_bytes, textract_client=textract_client)
        timings["ocr"] = time.time() - t0

        line_count = len(raw_text.strip().splitlines())
        if line_count >= MIN_OCR_LINES:
            # Textract got enough text — use LLM to structure it
            t0 = time.time()
            dishes = structure_menu(raw_text, bedrock_client=bedrock_client)
            timings["llm"] = time.time() - t0
            timings["extraction_method"] = "textract"
            return dishes
        else:
            logger.info("Textract returned only %d lines, falling back to vision", line_count)
    except OCRExtractionError:
        logger.info("Textract found no text, falling back to vision")

    # --- Fallback: send image directly to Claude vision ---
    t0 = time.time()
    dishes = structure_menu_from_image(image_bytes, bedrock_client=bedrock_client)
    timings["vision_extract"] = time.time() - t0
    timings["extraction_method"] = "vision"
    return dishes


def handler(
    event,
    context,
    s3_client=None,
    textract_client=None,
    bedrock_client=None,
) -> None:
    """
    Triggered by S3 event when image is uploaded.
    Runs the full pipeline with incremental result updates.
    Uses Textract for OCR when possible, falls back to Claude vision for unsupported scripts.
    """
    if s3_client is None:
        s3_client = boto3.client("s3", config=Config(signature_version="s3v4"))

    images_bucket = os.environ["IMAGES_BUCKET"]
    results_bucket = os.environ["RESULTS_BUCKET"]

    record = event["Records"][0]["s3"]
    source_bucket = record["bucket"]["name"]
    source_key = record["object"]["key"]
    job_id = source_key.split("/")[0]

    timings: dict[str, float] = {}

    try:
        # --- S3 read ---
        t0 = time.time()
        resp = s3_client.get_object(Bucket=source_bucket, Key=source_key)
        image_bytes = resp["Body"].read()
        timings["s3_read"] = time.time() - t0

        # --- Extract dishes (Textract → vision fallback) ---
        dishes = _extract_dishes(image_bytes, textract_client, bedrock_client, timings)

        if not dishes:
            timings["total"] = sum(v for v in timings.values() if isinstance(v, float))
            logger.info("TRACE job=%s timings=%s", job_id, timings)
            result = MenuResult(job_id=job_id, status=JobStatus.COMPLETED, dishes=[])
            store_results(results_bucket, job_id, result, s3_client=s3_client)
            return

        # Write intermediate result so frontend can show dish names while images generate
        intermediate = MenuResult(job_id=job_id, status=JobStatus.PROCESSING, dishes=dishes)
        store_results(results_bucket, job_id, intermediate, s3_client=s3_client)

        # --- Image generation (parallel, with incremental updates) ---
        t0 = time.time()
        any_failed = False
        completed_count = 0
        total_dishes = len(dishes)

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {
                executor.submit(
                    _generate_with_retry, idx, dish, bedrock_client
                ): idx
                for idx, dish in enumerate(dishes)
            }
            for future in as_completed(futures):
                idx, img_bytes = future.result()
                img_t0 = time.time()
                if img_bytes is not None:
                    url = store_image(
                        images_bucket, job_id, idx, img_bytes, s3_client=s3_client
                    )
                    dishes[idx].image_url = url
                else:
                    dishes[idx].image_url = PLACEHOLDER_IMAGE_URL
                    any_failed = True

                completed_count += 1
                inc_status = JobStatus.PROCESSING if completed_count < total_dishes else (
                    JobStatus.PARTIAL if any_failed else JobStatus.COMPLETED
                )
                inc_result = MenuResult(job_id=job_id, status=inc_status, dishes=dishes)
                store_results(results_bucket, job_id, inc_result, s3_client=s3_client)
                timings[f"image_{idx}"] = time.time() - img_t0

        timings["image_gen_total"] = time.time() - t0
        extract_time = timings.get("ocr", 0) + timings.get("llm", 0) + timings.get("vision_extract", 0)
        timings["total"] = timings["s3_read"] + extract_time + timings["image_gen_total"]
        logger.info("TRACE job=%s timings=%s", job_id, timings)

    except (OCRExtractionError, LLMProcessingError) as exc:
        logger.error("Pipeline failed for job %s: %s", job_id, exc)
        error_result = MenuResult(
            job_id=job_id,
            status=JobStatus.FAILED,
            error_message=str(exc),
        )
        store_results(results_bucket, job_id, error_result, s3_client=s3_client)

    except Exception as exc:
        logger.error("Unexpected error for job %s: %s", job_id, exc)
        error_result = MenuResult(
            job_id=job_id,
            status=JobStatus.FAILED,
            error_message=f"Processing failed: {exc}",
        )
        store_results(results_bucket, job_id, error_result, s3_client=s3_client)
