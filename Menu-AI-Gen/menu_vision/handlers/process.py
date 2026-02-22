"""Processing Lambda handler - triggered by S3 event, runs the full pipeline."""

from __future__ import annotations

import logging
import os

import boto3
from botocore.config import Config

from menu_vision.image_gen import generate_all_dish_images
from menu_vision.llm import LLMProcessingError, structure_menu
from menu_vision.models import JobStatus, MenuResult
from menu_vision.ocr import OCRExtractionError, extract_text
from menu_vision.storage import store_image, store_results

logger = logging.getLogger(__name__)

PLACEHOLDER_IMAGE_URL = "placeholder://no-image"


def handler(
    event,
    context,
    s3_client=None,
    textract_client=None,
    bedrock_client=None,
) -> None:
    """
    Triggered by S3 event when image is uploaded.
    Runs the full pipeline asynchronously.
    Event contains S3 bucket and key from the upload event.
    Writes MenuResult JSON to S3 when complete.
    """
    if s3_client is None:
        s3_client = boto3.client("s3", config=Config(signature_version="s3v4"))

    images_bucket = os.environ["IMAGES_BUCKET"]
    results_bucket = os.environ["RESULTS_BUCKET"]

    # Extract bucket/key from S3 event
    record = event["Records"][0]["s3"]
    source_bucket = record["bucket"]["name"]
    source_key = record["object"]["key"]

    # Extract job_id from key (format: {job_id}/menu_image)
    job_id = source_key.split("/")[0]

    try:
        # Read image from S3
        resp = s3_client.get_object(Bucket=source_bucket, Key=source_key)
        image_bytes = resp["Body"].read()

        # OCR
        raw_text = extract_text(image_bytes, textract_client=textract_client)

        # LLM structuring
        dishes = structure_menu(raw_text, bedrock_client=bedrock_client)

        if not dishes:
            result = MenuResult(job_id=job_id, status=JobStatus.COMPLETED, dishes=[])
            store_results(results_bucket, job_id, result, s3_client=s3_client)
            return

        # Parallel image generation
        image_results = generate_all_dish_images(dishes, bedrock_client=bedrock_client)

        any_failed = False
        for idx, img_bytes in image_results:
            if img_bytes is not None:
                url = store_image(
                    images_bucket, job_id, idx, img_bytes, s3_client=s3_client
                )
                dishes[idx].image_url = url
            else:
                dishes[idx].image_url = PLACEHOLDER_IMAGE_URL
                any_failed = True

        status = JobStatus.PARTIAL if any_failed else JobStatus.COMPLETED
        result = MenuResult(job_id=job_id, status=status, dishes=dishes)
        store_results(results_bucket, job_id, result, s3_client=s3_client)

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
