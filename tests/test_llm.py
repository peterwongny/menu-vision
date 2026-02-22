"""Unit tests for the LLM module."""

import json
from io import BytesIO
from unittest.mock import MagicMock

import pytest

from backend.llm import (
    LLMProcessingError,
    parse_llm_response,
    structure_menu,
)
from backend.models import DishRecord


class TestParseLlmResponse:
    """Tests for parse_llm_response()."""

    def test_parses_valid_json_array(self):
        """Parses a well-formed JSON array into DishRecord objects."""
        response = json.dumps([
            {
                "original_name": "Boeuf Bourguignon",
                "translated_name": "Beef Burgundy",
                "description": "Slow-braised beef in red wine",
                "ingredients": ["beef", "red wine", "carrots"],
                "price": "€24.50",
            }
        ])

        dishes = parse_llm_response(response)

        assert len(dishes) == 1
        assert dishes[0].original_name == "Boeuf Bourguignon"
        assert dishes[0].translated_name == "Beef Burgundy"
        assert dishes[0].description == "Slow-braised beef in red wine"
        assert dishes[0].ingredients == ["beef", "red wine", "carrots"]
        assert dishes[0].price == "€24.50"
        assert dishes[0].image_url is None

    def test_parses_json_from_markdown_code_block(self):
        """Extracts JSON from markdown ```json code blocks."""
        response = '```json\n[{"original_name": "Pasta"}]\n```'

        dishes = parse_llm_response(response)

        assert len(dishes) == 1
        assert dishes[0].original_name == "Pasta"

    def test_parses_json_from_plain_code_block(self):
        """Extracts JSON from markdown ``` code blocks without language tag."""
        response = '```\n[{"original_name": "Ramen"}]\n```'

        dishes = parse_llm_response(response)

        assert len(dishes) == 1
        assert dishes[0].original_name == "Ramen"

    def test_null_fields_become_none(self):
        """Null JSON fields map to None on DishRecord."""
        response = json.dumps([
            {
                "original_name": "Mystery Dish",
                "translated_name": None,
                "description": None,
                "ingredients": None,
                "price": None,
            }
        ])

        dishes = parse_llm_response(response)

        assert len(dishes) == 1
        assert dishes[0].translated_name is None
        assert dishes[0].description is None
        assert dishes[0].ingredients == []
        assert dishes[0].price is None

    def test_missing_fields_become_none_or_defaults(self):
        """Missing JSON fields map to None or default values."""
        response = json.dumps([{"original_name": "Simple Dish"}])

        dishes = parse_llm_response(response)

        assert len(dishes) == 1
        assert dishes[0].translated_name is None
        assert dishes[0].description is None
        assert dishes[0].ingredients == []
        assert dishes[0].price is None

    def test_skips_entries_without_original_name(self):
        """Entries missing original_name are skipped."""
        response = json.dumps([
            {"original_name": "Valid Dish"},
            {"translated_name": "No Name"},
            {"original_name": "", "translated_name": "Empty Name"},
        ])

        dishes = parse_llm_response(response)

        assert len(dishes) == 1
        assert dishes[0].original_name == "Valid Dish"

    def test_skips_non_dict_entries(self):
        """Non-dict entries in the array are skipped."""
        response = json.dumps([
            "not a dish",
            42,
            {"original_name": "Real Dish"},
        ])

        dishes = parse_llm_response(response)

        assert len(dishes) == 1
        assert dishes[0].original_name == "Real Dish"

    def test_raises_on_invalid_json(self):
        """Raises LLMProcessingError on unparseable JSON."""
        with pytest.raises(LLMProcessingError, match="Failed to parse"):
            parse_llm_response("this is not json at all")

    def test_raises_on_json_object_instead_of_array(self):
        """Raises LLMProcessingError when response is a JSON object, not array."""
        with pytest.raises(LLMProcessingError, match="Expected JSON array"):
            parse_llm_response('{"original_name": "Dish"}')

    def test_empty_array_returns_empty_list(self):
        """An empty JSON array returns an empty list."""
        dishes = parse_llm_response("[]")
        assert dishes == []

    def test_strips_whitespace_from_original_name(self):
        """Whitespace is stripped from original_name."""
        response = json.dumps([{"original_name": "  Padded Name  "}])

        dishes = parse_llm_response(response)

        assert dishes[0].original_name == "Padded Name"

    def test_filters_none_from_ingredients(self):
        """None values inside ingredients list are filtered out."""
        response = json.dumps([
            {"original_name": "Dish", "ingredients": ["beef", None, "onion"]}
        ])

        dishes = parse_llm_response(response)

        assert dishes[0].ingredients == ["beef", "onion"]

    def test_multiple_dishes(self):
        """Parses multiple dishes correctly."""
        response = json.dumps([
            {"original_name": "Dish A", "price": "$10"},
            {"original_name": "Dish B", "price": "$15"},
            {"original_name": "Dish C", "price": "$20"},
        ])

        dishes = parse_llm_response(response)

        assert len(dishes) == 3
        assert [d.original_name for d in dishes] == ["Dish A", "Dish B", "Dish C"]


class TestStructureMenu:
    """Tests for structure_menu()."""

    def _make_mock_client(self, response_dishes):
        """Create a mock Bedrock client that returns the given dishes as Claude response."""
        mock_client = MagicMock()
        response_body = json.dumps({
            "content": [
                {"type": "text", "text": json.dumps(response_dishes)}
            ]
        }).encode()
        mock_client.invoke_model.return_value = {
            "body": BytesIO(response_body)
        }
        return mock_client

    def test_calls_bedrock_and_returns_dishes(self):
        """Calls invoke_model and parses the response into DishRecords."""
        mock_client = self._make_mock_client([
            {
                "original_name": "Soupe à l'oignon",
                "translated_name": "French Onion Soup",
                "description": "Classic onion soup with cheese",
                "ingredients": ["onion", "cheese", "bread"],
                "price": "€12",
            }
        ])

        dishes = structure_menu("Soupe à l'oignon\n€12", bedrock_client=mock_client)

        assert len(dishes) == 1
        assert dishes[0].original_name == "Soupe à l'oignon"
        assert dishes[0].translated_name == "French Onion Soup"
        mock_client.invoke_model.assert_called_once()

    def test_passes_correct_model_id(self):
        """Uses the correct Claude model ID."""
        mock_client = self._make_mock_client([{"original_name": "Test"}])

        structure_menu("menu text", bedrock_client=mock_client)

        call_kwargs = mock_client.invoke_model.call_args[1]
        assert call_kwargs["modelId"] == "anthropic.claude-3-haiku-20240307-v1:0"

    def test_raises_on_bedrock_api_error(self):
        """Raises LLMProcessingError when Bedrock API call fails."""
        mock_client = MagicMock()
        mock_client.invoke_model.side_effect = Exception("Service unavailable")

        with pytest.raises(LLMProcessingError, match="Bedrock invoke_model failed"):
            structure_menu("some text", bedrock_client=mock_client)

    def test_raises_on_empty_response_content(self):
        """Raises LLMProcessingError when Claude returns no text content."""
        mock_client = MagicMock()
        response_body = json.dumps({"content": []}).encode()
        mock_client.invoke_model.return_value = {"body": BytesIO(response_body)}

        with pytest.raises(LLMProcessingError, match="No text content"):
            structure_menu("some text", bedrock_client=mock_client)

    def test_raises_on_malformed_response_body(self):
        """Raises LLMProcessingError when response body is not valid JSON."""
        mock_client = MagicMock()
        mock_client.invoke_model.return_value = {"body": BytesIO(b"not json")}

        with pytest.raises(LLMProcessingError, match="Failed to read Bedrock response"):
            structure_menu("some text", bedrock_client=mock_client)

    def test_unknown_fields_are_none(self):
        """Fields Claude marks as null come through as None on DishRecord."""
        mock_client = self._make_mock_client([
            {
                "original_name": "Unknown Dish",
                "translated_name": None,
                "description": None,
                "ingredients": [],
                "price": None,
            }
        ])

        dishes = structure_menu("Unknown Dish", bedrock_client=mock_client)

        assert dishes[0].translated_name is None
        assert dishes[0].description is None
        assert dishes[0].price is None
        assert dishes[0].ingredients == []
