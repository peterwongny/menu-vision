"""Image generation module - creates photorealistic dish images using Amazon Bedrock."""

from __future__ import annotations

import base64
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import boto3
from botocore.exceptions import ClientError

from backend.models import DishRecord

IMAGE_MODEL_ID = os.environ.get("IMAGE_MODEL_ID", "stability.stable-image-core-v1:1")
MAX_WORKERS = int(os.environ.get("IMAGE_GEN_WORKERS", "10"))

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_BASE_DELAY = 1.0  # seconds


class ImageGenerationError(Exception):
    """Raised when image generation fails."""


def build_image_prompt(dish: DishRecord) -> str:
    """
    Constructs a cuisine-aware, richly descriptive prompt for the image generator.
    Uses the dish's cuisine, description, and ingredients to guide the model
    toward an authentic, photorealistic result.
    """
    name = dish.translated_name if dish.translated_name else dish.original_name
    cuisine = dish.cuisine or ""

    # Lead with cuisine context so the model anchors on the right visual style
    if cuisine:
        parts = [f"Professional food photography of authentic {cuisine} dish: {name}."]
    else:
        parts = [f"Professional food photography of {name}."]

    if dish.description:
        parts.append(dish.description)

    if dish.ingredients:
        parts.append(f"Made with {', '.join(dish.ingredients)}.")

    # Cuisine-specific styling cues
    if cuisine:
        parts.append(f"Served in traditional {cuisine} style with appropriate plating and tableware.")

    parts.append(
        "Shot from 45-degree angle, shallow depth of field, warm natural lighting, "
        "on a clean restaurant table, 4K, ultra detailed."
    )

    return " ".join(parts)


def generate_dish_image(dish: DishRecord, bedrock_client=None) -> bytes:
    """
    Generates a photorealistic image for a dish using Bedrock.
    Model is configurable via IMAGE_MODEL_ID env var.
    Returns image bytes (PNG).
    Raises: ImageGenerationError on failure.
    """
    if bedrock_client is None:
        bedrock_client = boto3.client("bedrock-runtime")

    prompt = build_image_prompt(dish)

    request_body = json.dumps({"prompt": prompt})

    try:
        response = bedrock_client.invoke_model(
            modelId=IMAGE_MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=request_body,
        )
    except Exception as e:
        raise ImageGenerationError(f"Bedrock invoke_model failed: {e}") from e

    try:
        response_body = json.loads(response["body"].read())
    except (json.JSONDecodeError, KeyError) as e:
        raise ImageGenerationError(f"Failed to read Bedrock response: {e}") from e

    images = response_body.get("images")
    if not images:
        raise ImageGenerationError("No images returned in Bedrock response")

    try:
        image_bytes = base64.b64decode(images[0])
    except Exception as e:
        raise ImageGenerationError(f"Failed to decode base64 image: {e}") from e

    return image_bytes

def _generate_with_retry(
    index: int, dish: DishRecord, bedrock_client=None
) -> tuple[int, bytes | None]:
    """Generate an image for a single dish with retry on throttling.

    Returns (dish_index, image_bytes) on success or (dish_index, None) on failure.
    """
    for attempt in range(_MAX_RETRIES):
        try:
            image_bytes = generate_dish_image(dish, bedrock_client=bedrock_client)
            return (index, image_bytes)
        except ImageGenerationError as e:
            cause = e.__cause__
            if (
                isinstance(cause, ClientError)
                and cause.response.get("Error", {}).get("Code") == "ThrottlingException"
            ):
                delay = _BASE_DELAY * (2 ** attempt)
                logger.warning(
                    "ThrottlingException for dish %d (attempt %d/%d), retrying in %.1fs",
                    index,
                    attempt + 1,
                    _MAX_RETRIES,
                    delay,
                )
                time.sleep(delay)
                continue
            # Non-throttling error — give up immediately
            logger.error("Image generation failed for dish %d: %s", index, e)
            return (index, None)
        except Exception as e:
            logger.error("Unexpected error for dish %d: %s", index, e)
            return (index, None)

    # All retries exhausted
    logger.error("All %d retries exhausted for dish %d", _MAX_RETRIES, index)
    return (index, None)


def generate_all_dish_images(
    dishes: list[DishRecord], bedrock_client=None
) -> list[tuple[int, bytes | None]]:
    """
    Generates images for all dishes in parallel using a thread pool.
    Returns list of (dish_index, image_bytes_or_None) tuples sorted by dish_index.
    Failed dishes return None instead of raising.
    """
    results: list[tuple[int, bytes | None]] = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(
                _generate_with_retry, idx, dish, bedrock_client
            ): idx
            for idx, dish in enumerate(dishes)
        }
        for future in as_completed(futures):
            results.append(future.result())

    results.sort(key=lambda r: r[0])
    return results

