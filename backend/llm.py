"""LLM module - structures and translates menu text using Amazon Bedrock Claude."""

from __future__ import annotations

import json
import re
from typing import Optional

import boto3

from backend.models import DishRecord

MODEL_ID = "us.anthropic.claude-haiku-4-5-20251001-v1:0"

SYSTEM_PROMPT = """You are a menu analysis assistant. Given a restaurant menu (as text or image), identify each individual dish and extract structured information.

For each dish, provide:
- original_name: The dish name exactly as it appears on the menu
- translated_name: The dish name translated to English (set to null if already in English)
- description: A brief description of the dish from the menu (set to null if not available)
- ingredients: A list of ingredients mentioned or clearly implied (use an empty list if unknown)
- price: The price as shown on the menu including currency symbol (set to null if not available)

IMPORTANT RULES:
- Output ONLY a JSON array of dish objects. No other text.
- Use null for any field you cannot determine from the text. NEVER fabricate or guess values.
- If the menu is not in English, translate dish names and descriptions to English.
- Keep original_name in the original language exactly as written.
- Each dish must have an original_name. Skip entries that are not dishes (e.g., section headers, restaurant info).
"""


class LLMProcessingError(Exception):
    """Raised when LLM processing fails."""


def parse_llm_response(response_text: str) -> list[DishRecord]:
    """
    Parses the JSON response from Claude into DishRecord objects.

    Handles:
    - Valid JSON arrays directly
    - JSON embedded in markdown code blocks (```json ... ```)
    - Null/missing fields gracefully
    """
    text = response_text.strip()

    # Extract JSON from markdown code blocks if present
    code_block_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if code_block_match:
        text = code_block_match.group(1).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # LLM response may be truncated — try to recover partial JSON array
        data = _recover_truncated_json(text)
        if data is None:
            raise LLMProcessingError(
                f"Failed to parse LLM response as JSON and could not recover partial array"
            )

    if not isinstance(data, list):
        raise LLMProcessingError(
            f"Expected JSON array from LLM, got {type(data).__name__}"
        )

    dishes = []
    for item in data:
        if not isinstance(item, dict):
            continue

        original_name = item.get("original_name")
        if not original_name or not isinstance(original_name, str):
            continue  # Skip entries without a valid original_name

        raw_ingredients = item.get("ingredients")
        if isinstance(raw_ingredients, list):
            ingredients = [str(i) for i in raw_ingredients if i is not None]
        else:
            ingredients = []

        dish = DishRecord(
            original_name=original_name.strip(),
            translated_name=_nullable_str(item.get("translated_name")),
            description=_nullable_str(item.get("description")),
            ingredients=ingredients,
            price=_nullable_str(item.get("price")),
        )
        dishes.append(dish)

    return dishes


def structure_menu(
    raw_text: str, bedrock_client=None
) -> list[DishRecord]:
    """
    Sends raw OCR text to Bedrock Claude.
    Returns a list of structured DishRecord objects.
    Raises: LLMProcessingError on failure.
    """
    if bedrock_client is None:
        bedrock_client = boto3.client("bedrock-runtime")

    request_body = json.dumps(
        {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 16384,
            "system": SYSTEM_PROMPT,
            "messages": [
                {
                    "role": "user",
                    "content": f"Extract dishes from this menu text:\n\n{raw_text}",
                }
            ],
        }
    )

    try:
        response = bedrock_client.invoke_model(
            modelId=MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=request_body,
        )
    except Exception as e:
        raise LLMProcessingError(f"Bedrock invoke_model failed: {e}") from e

    try:
        response_body = json.loads(response["body"].read())
    except (json.JSONDecodeError, KeyError) as e:
        raise LLMProcessingError(f"Failed to read Bedrock response: {e}") from e

    # Extract text content from Claude's response
    content_blocks = response_body.get("content", [])
    text_parts = [
        block["text"] for block in content_blocks if block.get("type") == "text"
    ]

    if not text_parts:
        raise LLMProcessingError("No text content in Bedrock Claude response")

    response_text = "\n".join(text_parts)
    return parse_llm_response(response_text)


def structure_menu_from_image(
    image_bytes: bytes, bedrock_client=None, media_type: str = "image/jpeg"
) -> list[DishRecord]:
    """
    Sends a menu image directly to Claude for vision-based extraction.
    Skips OCR entirely — Claude reads the image natively.
    Compresses image if over 4.5MB to stay under Claude's 5MB limit.
    Returns a list of structured DishRecord objects.
    """
    if bedrock_client is None:
        bedrock_client = boto3.client("bedrock-runtime")

    import base64

    # Compress if needed to stay under Claude's 5MB image limit
    MAX_IMAGE_SIZE = 4_500_000  # 4.5MB with margin
    if len(image_bytes) > MAX_IMAGE_SIZE:
        image_bytes = _compress_image(image_bytes, MAX_IMAGE_SIZE)
        media_type = "image/jpeg"

    encoded = base64.b64encode(image_bytes).decode("utf-8")

    request_body = json.dumps(
        {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 16384,
            "system": SYSTEM_PROMPT,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": encoded,
                            },
                        },
                        {
                            "type": "text",
                            "text": "Extract all dishes from this menu image.",
                        },
                    ],
                }
            ],
        }
    )

    try:
        response = bedrock_client.invoke_model(
            modelId=MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=request_body,
        )
    except Exception as e:
        raise LLMProcessingError(f"Bedrock invoke_model failed: {e}") from e

    try:
        response_body = json.loads(response["body"].read())
    except (json.JSONDecodeError, KeyError) as e:
        raise LLMProcessingError(f"Failed to read Bedrock response: {e}") from e

    content_blocks = response_body.get("content", [])
    text_parts = [
        block["text"] for block in content_blocks if block.get("type") == "text"
    ]

    if not text_parts:
        raise LLMProcessingError("No text content in Bedrock Claude response")

    response_text = "\n".join(text_parts)
    return parse_llm_response(response_text)


def _compress_image(image_bytes: bytes, max_size: int) -> bytes:
    """Resize and compress an image to fit under max_size bytes."""
    import io
    from PIL import Image

    img = Image.open(io.BytesIO(image_bytes))
    img = img.convert("RGB")  # Ensure JPEG-compatible mode

    # First try: just re-encode as JPEG with decreasing quality
    for quality in (85, 70, 50, 30):
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        if buf.tell() <= max_size:
            return buf.getvalue()

    # Still too big — resize down
    for scale in (0.75, 0.5, 0.35):
        w, h = int(img.width * scale), int(img.height * scale)
        resized = img.resize((w, h), Image.LANCZOS)
        buf = io.BytesIO()
        resized.save(buf, format="JPEG", quality=60)
        if buf.tell() <= max_size:
            return buf.getvalue()

    # Last resort: aggressive resize
    resized = img.resize((1024, int(1024 * img.height / img.width)), Image.LANCZOS)
    buf = io.BytesIO()
    resized.save(buf, format="JPEG", quality=50)
    return buf.getvalue()


def _recover_truncated_json(text: str) -> Optional[list]:
    """Try to recover a truncated JSON array by finding the last complete object."""
    # Find all complete JSON objects in the text
    depth = 0
    last_complete = -1
    in_string = False
    escape_next = False

    for i, ch in enumerate(text):
        if escape_next:
            escape_next = False
            continue
        if ch == '\\' and in_string:
            escape_next = True
            continue
        if ch == '"' and not escape_next:
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                last_complete = i

    if last_complete <= 0:
        return None

    # Truncate after the last complete object and close the array
    truncated = text[:last_complete + 1].rstrip().rstrip(',') + ']'
    # Ensure it starts with [
    bracket_pos = truncated.find('[')
    if bracket_pos == -1:
        return None
    truncated = truncated[bracket_pos:]

    try:
        data = json.loads(truncated)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass
    return None


def _nullable_str(value) -> Optional[str]:
    """Return a stripped string or None if the value is falsy or not a string."""
    if value is None:
        return None
    if not isinstance(value, str):
        return str(value)
    stripped = value.strip()
    return stripped if stripped else None
