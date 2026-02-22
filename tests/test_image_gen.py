"""Unit tests for image generation module (build_image_prompt and generate_dish_image)."""

import base64
import io
import json

import pytest

from backend.image_gen import (
    ImageGenerationError,
    build_image_prompt,
    generate_dish_image,
)
from backend.models import DishRecord


# --- build_image_prompt tests ---


class TestBuildImagePrompt:
    def test_basic_dish_with_all_fields(self):
        dish = DishRecord(
            original_name="Boeuf Bourguignon",
            translated_name="Beef Burgundy",
            description="Slow-braised beef in red wine",
            ingredients=["beef", "red wine", "carrots"],
        )
        prompt = build_image_prompt(dish)
        assert "Professional food photography of Beef Burgundy." in prompt
        assert "Slow-braised beef in red wine." in prompt
        assert "Ingredients: beef, red wine, carrots." in prompt
        assert "Photorealistic, high quality, restaurant presentation, soft lighting." in prompt

    def test_uses_translated_name_when_available(self):
        dish = DishRecord(
            original_name="Crème Brûlée",
            translated_name="Cream Brulee",
        )
        prompt = build_image_prompt(dish)
        assert "Cream Brulee" in prompt
        assert "Crème Brûlée" not in prompt

    def test_falls_back_to_original_name_when_no_translation(self):
        dish = DishRecord(original_name="Caesar Salad")
        prompt = build_image_prompt(dish)
        assert "Caesar Salad" in prompt

    def test_no_description(self):
        dish = DishRecord(original_name="Pasta", description=None)
        prompt = build_image_prompt(dish)
        # Should not have an empty sentence or "None"
        assert "None" not in prompt
        assert "Professional food photography of Pasta." in prompt

    def test_no_ingredients(self):
        dish = DishRecord(original_name="Soup", ingredients=[])
        prompt = build_image_prompt(dish)
        assert "Ingredients:" not in prompt

    def test_minimal_dish_only_name(self):
        dish = DishRecord(original_name="Bread")
        prompt = build_image_prompt(dish)
        assert prompt == (
            "Professional food photography of Bread. "
            "Photorealistic, high quality, restaurant presentation, soft lighting."
        )


# --- generate_dish_image tests ---


class TestGenerateDishImage:
    def _make_mock_client(self, image_bytes: bytes):
        """Create a mock Bedrock client that returns the given image bytes."""
        encoded = base64.b64encode(image_bytes).decode("utf-8")
        response_body = json.dumps({"images": [encoded]}).encode("utf-8")

        class MockBody:
            def __init__(self, data):
                self._stream = io.BytesIO(data)

            def read(self):
                return self._stream.read()

        class MockClient:
            def invoke_model(self, **kwargs):
                return {"body": MockBody(response_body)}

        return MockClient()

    def test_returns_decoded_image_bytes(self):
        expected_bytes = b"\x89PNG\r\n\x1a\nfake_image_data"
        client = self._make_mock_client(expected_bytes)
        dish = DishRecord(original_name="Test Dish")

        result = generate_dish_image(dish, bedrock_client=client)
        assert result == expected_bytes

    def test_raises_on_invoke_failure(self):
        class FailingClient:
            def invoke_model(self, **kwargs):
                raise RuntimeError("Service unavailable")

        dish = DishRecord(original_name="Test Dish")
        with pytest.raises(ImageGenerationError, match="Bedrock invoke_model failed"):
            generate_dish_image(dish, bedrock_client=FailingClient())

    def test_raises_on_empty_images(self):
        response_body = json.dumps({"images": []}).encode("utf-8")

        class MockBody:
            def read(self):
                return response_body

        class MockClient:
            def invoke_model(self, **kwargs):
                return {"body": MockBody()}

        dish = DishRecord(original_name="Test Dish")
        with pytest.raises(ImageGenerationError, match="No images returned"):
            generate_dish_image(dish, bedrock_client=MockClient())

    def test_raises_on_malformed_response(self):
        class MockBody:
            def read(self):
                return b"not json"

        class MockClient:
            def invoke_model(self, **kwargs):
                return {"body": MockBody()}

        dish = DishRecord(original_name="Test Dish")
        with pytest.raises(ImageGenerationError, match="Failed to read Bedrock response"):
            generate_dish_image(dish, bedrock_client=MockClient())

    def test_raises_on_invalid_base64(self):
        response_body = json.dumps({"images": ["!!!not-base64!!!"]}).encode("utf-8")

        class MockBody:
            def read(self):
                return response_body

        class MockClient:
            def invoke_model(self, **kwargs):
                return {"body": MockBody()}

        dish = DishRecord(original_name="Test Dish")
        with pytest.raises(ImageGenerationError, match="Failed to decode base64 image"):
            generate_dish_image(dish, bedrock_client=MockClient())

    def test_passes_correct_model_id_and_body(self):
        """Verify the request body structure sent to Bedrock."""
        captured = {}

        class CapturingClient:
            def invoke_model(self, **kwargs):
                captured.update(kwargs)
                encoded = base64.b64encode(b"img").decode("utf-8")
                body = json.dumps({"images": [encoded]}).encode("utf-8")

                class MockBody:
                    def read(self):
                        return body

                return {"body": MockBody()}

        dish = DishRecord(
            original_name="Ramen",
            description="Japanese noodle soup",
            ingredients=["noodles", "broth"],
        )
        generate_dish_image(dish, bedrock_client=CapturingClient())

        assert captured["contentType"] == "application/json"
        assert captured["accept"] == "application/json"

        sent_body = json.loads(captured["body"])
        assert "prompt" in sent_body
        assert "Ramen" in sent_body["prompt"]


# --- Tests for generate_all_dish_images and retry logic ---

import time
from unittest.mock import patch

from botocore.exceptions import ClientError

from backend.image_gen import (
    MAX_WORKERS,
    _BASE_DELAY,
    _MAX_RETRIES,
    _generate_with_retry,
    generate_all_dish_images,
)


def _make_success_client(image_bytes: bytes = b"fake_png"):
    """Create a mock Bedrock client that always succeeds."""
    encoded = base64.b64encode(image_bytes).decode("utf-8")
    response_body = json.dumps({"images": [encoded]}).encode("utf-8")

    class MockBody:
        def read(self):
            return response_body

    class MockClient:
        def invoke_model(self, **kwargs):
            return {"body": MockBody()}

    return MockClient()


def _make_throttling_error():
    """Create a ClientError that looks like a ThrottlingException."""
    return ClientError(
        error_response={"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
        operation_name="InvokeModel",
    )


def _make_failing_client(error: Exception):
    """Create a mock Bedrock client that always raises the given error."""

    class MockClient:
        def invoke_model(self, **kwargs):
            raise error

    return MockClient()


def _make_mixed_client(success_indices: set[int], image_bytes: bytes = b"fake_png"):
    """Create a mock client that succeeds for given indices and fails for others.

    Uses a call counter to determine which dish index is being processed.
    """
    encoded = base64.b64encode(image_bytes).decode("utf-8")
    response_body = json.dumps({"images": [encoded]}).encode("utf-8")
    call_count = {"n": 0}

    class MockBody:
        def read(self):
            return response_body

    class MockClient:
        def invoke_model(self, **kwargs):
            idx = call_count["n"]
            call_count["n"] += 1
            if idx in success_indices:
                return {"body": MockBody()}
            raise RuntimeError("Service unavailable")

    return MockClient()


class TestGenerateAllDishImages:
    def _make_dishes(self, n: int) -> list[DishRecord]:
        return [DishRecord(original_name=f"Dish {i}") for i in range(n)]

    def test_all_succeed(self):
        dishes = self._make_dishes(3)
        client = _make_success_client(b"img_data")
        results = generate_all_dish_images(dishes, bedrock_client=client)

        assert len(results) == 3
        for idx, img in results:
            assert img == b"img_data"
        # Verify sorted by index
        assert [r[0] for r in results] == [0, 1, 2]

    def test_empty_dish_list(self):
        results = generate_all_dish_images([], bedrock_client=_make_success_client())
        assert results == []

    def test_single_dish(self):
        dishes = self._make_dishes(1)
        client = _make_success_client(b"single")
        results = generate_all_dish_images(dishes, bedrock_client=client)
        assert len(results) == 1
        assert results[0] == (0, b"single")

    def test_failed_dishes_return_none(self):
        """When a non-throttling error occurs, the dish should return None."""
        dishes = self._make_dishes(3)
        client = _make_failing_client(RuntimeError("boom"))
        results = generate_all_dish_images(dishes, bedrock_client=client)

        assert len(results) == 3
        for idx, img in results:
            assert img is None

    def test_results_sorted_by_index(self):
        """Results should always be sorted by dish index regardless of completion order."""
        dishes = self._make_dishes(5)
        client = _make_success_client(b"data")
        results = generate_all_dish_images(dishes, bedrock_client=client)
        indices = [r[0] for r in results]
        assert indices == list(range(5))


class TestGenerateWithRetry:
    def test_success_on_first_attempt(self):
        dish = DishRecord(original_name="Test")
        client = _make_success_client(b"ok")
        idx, img = _generate_with_retry(0, dish, bedrock_client=client)
        assert idx == 0
        assert img == b"ok"

    def test_non_throttling_error_returns_none_immediately(self):
        dish = DishRecord(original_name="Test")
        client = _make_failing_client(RuntimeError("not throttling"))
        idx, img = _generate_with_retry(0, dish, bedrock_client=client)
        assert idx == 0
        assert img is None

    @patch("backend.image_gen.time.sleep")
    def test_throttling_retries_with_backoff(self, mock_sleep):
        """On ThrottlingException, should retry with exponential backoff."""
        throttle_err = _make_throttling_error()
        call_count = {"n": 0}

        encoded = base64.b64encode(b"success").decode("utf-8")
        success_body = json.dumps({"images": [encoded]}).encode("utf-8")

        class MockBody:
            def read(self):
                return success_body

        class RetryClient:
            def invoke_model(self, **kwargs):
                call_count["n"] += 1
                if call_count["n"] <= 2:
                    raise throttle_err
                return {"body": MockBody()}

        dish = DishRecord(original_name="Test")
        idx, img = _generate_with_retry(0, dish, bedrock_client=RetryClient())

        assert idx == 0
        assert img == b"success"
        assert call_count["n"] == 3
        # Verify exponential backoff delays
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(_BASE_DELAY * 1)   # 2^0
        mock_sleep.assert_any_call(_BASE_DELAY * 2)    # 2^1

    @patch("backend.image_gen.time.sleep")
    def test_throttling_exhausts_retries_returns_none(self, mock_sleep):
        """If all retries are exhausted due to throttling, return None."""
        throttle_err = _make_throttling_error()

        class AlwaysThrottleClient:
            def invoke_model(self, **kwargs):
                raise throttle_err

        dish = DishRecord(original_name="Test")
        idx, img = _generate_with_retry(0, dish, bedrock_client=AlwaysThrottleClient())

        assert idx == 0
        assert img is None
        assert mock_sleep.call_count == _MAX_RETRIES
