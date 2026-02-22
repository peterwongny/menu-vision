"""LLM module - structures and translates menu text using Amazon Bedrock Claude."""

from __future__ import annotations

import json
import re
from typing import Optional

import boto3

from menu_vision.models import DishRecord

MODEL_ID = "anthropic.claude-3-haiku-20240307-v1:0"

SYSTEM_PROMPT = """You are a menu analysis assistant. Given raw text extracted from a restaurant menu via OCR, identify each individual dish and extract structured information.

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
    except json.JSONDecodeError as e:
        raise LLMProcessingError(f"Failed to parse LLM response as JSON: {e}")

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
            "max_tokens": 4096,
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


def _nullable_str(value) -> Optional[str]:
    """Return a stripped string or None if the value is falsy or not a string."""
    if value is None:
        return None
    if not isinstance(value, str):
        return str(value)
    stripped = value.strip()
    return stripped if stripped else None
