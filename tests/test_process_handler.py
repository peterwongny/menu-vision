"""Unit tests for the Processing Lambda handler."""

import json
import os
from io import BytesIO
from unittest.mock import MagicMock, patch

import boto3
import pytest
from moto import mock_aws

from backend.handlers.process import handler
from backend.models import DishRecord, JobStatus
from backend.storage import get_results

UPLOAD_BUCKET = "test-uploads"
IMAGES_BUCKET = "test-images"
RESULTS_BUCKET = "test-results"
JOB_ID = "abc-123"
IMAGE_BYTES = b"\x89PNG\r\nfake-menu-image"


def _s3_event(bucket: str = UPLOAD_BUCKET, key: str = f"{JOB_ID}/menu_image") -> dict:
    return {
        "Records": [
            {
                "s3": {
                    "bucket": {"name": bucket},
                    "object": {"key": key},
                }
            }
        ]
    }


@pytest.fixture
def aws_env(monkeypatch):
    monkeypatch.setenv("IMAGES_BUCKET", IMAGES_BUCKET)
    monkeypatch.setenv("RESULTS_BUCKET", RESULTS_BUCKET)


@pytest.fixture
def s3_client():
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=UPLOAD_BUCKET)
        client.create_bucket(Bucket=IMAGES_BUCKET)
        client.create_bucket(Bucket=RESULTS_BUCKET)
        # Upload a fake menu image
        client.put_object(
            Bucket=UPLOAD_BUCKET,
            Key=f"{JOB_ID}/menu_image",
            Body=IMAGE_BYTES,
        )
        yield client


def _mock_textract():
    mock = MagicMock()
    mock.detect_document_text.return_value = {
        "Blocks": [
            {"BlockType": "LINE", "Text": "Boeuf Bourguignon €24"},
            {"BlockType": "LINE", "Text": "Slow-braised beef in red wine"},
        ]
    }
    return mock


def _mock_bedrock(dish_count: int = 1):
    """Return a mock bedrock client that handles both LLM and image gen calls."""
    mock = MagicMock()

    dishes_json = json.dumps(
        [
            {
                "original_name": f"Dish {i}",
                "translated_name": f"Dish {i} EN",
                "description": f"Description {i}",
                "ingredients": ["ingredient"],
                "price": f"€{10 + i}",
            }
            for i in range(dish_count)
        ]
    )

    llm_response = {
        "content": [{"type": "text", "text": dishes_json}],
    }

    import base64

    fake_image = base64.b64encode(b"fake-png-bytes").decode()
    image_response = {"images": [fake_image]}

    def invoke_model(**kwargs):
        body_str = kwargs.get("body", "{}")
        body = json.loads(body_str) if isinstance(body_str, str) else body_str

        # LLM call has "messages" key, image gen has "taskType"
        if "messages" in body:
            resp_bytes = json.dumps(llm_response).encode()
        else:
            resp_bytes = json.dumps(image_response).encode()

        return {"body": BytesIO(resp_bytes)}

    mock.invoke_model.side_effect = invoke_model
    return mock


class TestProcessHandler:
    def test_successful_pipeline_stores_completed_result(self, aws_env, s3_client):
        textract = _mock_textract()
        bedrock = _mock_bedrock(dish_count=1)

        handler(
            _s3_event(),
            None,
            s3_client=s3_client,
            textract_client=textract,
            bedrock_client=bedrock,
        )

        result = get_results(RESULTS_BUCKET, JOB_ID, s3_client=s3_client)
        assert result is not None
        assert result.job_id == JOB_ID
        assert result.status == JobStatus.COMPLETED
        assert len(result.dishes) == 1
        assert result.dishes[0].original_name == "Dish 0"
        # Image URL should be a real pre-signed URL, not a placeholder
        assert result.dishes[0].image_url is not None
        assert "placeholder" not in result.dishes[0].image_url

    def test_stores_dish_images_in_images_bucket(self, aws_env, s3_client):
        textract = _mock_textract()
        bedrock = _mock_bedrock(dish_count=2)

        handler(
            _s3_event(),
            None,
            s3_client=s3_client,
            textract_client=textract,
            bedrock_client=bedrock,
        )

        # Verify images were stored
        for i in range(2):
            obj = s3_client.get_object(
                Bucket=IMAGES_BUCKET, Key=f"{JOB_ID}/dish_{i}.png"
            )
            assert obj["Body"].read() == b"fake-png-bytes"

    def test_vision_failure_writes_failed_result(self, aws_env, s3_client):
        bedrock = MagicMock()
        bedrock.invoke_model.side_effect = Exception("Bedrock down")

        handler(
            _s3_event(),
            None,
            s3_client=s3_client,
            bedrock_client=bedrock,
        )

        result = get_results(RESULTS_BUCKET, JOB_ID, s3_client=s3_client)
        assert result is not None
        assert result.status == JobStatus.FAILED
        assert result.error_message is not None

    def test_llm_failure_writes_failed_result(self, aws_env, s3_client):
        bedrock = MagicMock()
        bedrock.invoke_model.side_effect = Exception("Bedrock down")

        handler(
            _s3_event(),
            None,
            s3_client=s3_client,
            bedrock_client=bedrock,
        )

        result = get_results(RESULTS_BUCKET, JOB_ID, s3_client=s3_client)
        assert result is not None
        assert result.status == JobStatus.FAILED
        assert result.error_message is not None

    def test_extracts_job_id_from_s3_key(self, aws_env, s3_client):
        custom_job_id = "custom-job-42"
        s3_client.put_object(
            Bucket=UPLOAD_BUCKET,
            Key=f"{custom_job_id}/menu_image",
            Body=IMAGE_BYTES,
        )

        textract = _mock_textract()
        bedrock = _mock_bedrock(dish_count=1)

        handler(
            _s3_event(key=f"{custom_job_id}/menu_image"),
            None,
            s3_client=s3_client,
            textract_client=textract,
            bedrock_client=bedrock,
        )

        result = get_results(RESULTS_BUCKET, custom_job_id, s3_client=s3_client)
        assert result is not None
        assert result.job_id == custom_job_id

    def test_empty_dishes_stores_completed_with_no_dishes(self, aws_env, s3_client):
        textract = _mock_textract()
        bedrock = MagicMock()

        empty_response = {"content": [{"type": "text", "text": "[]"}]}

        bedrock.invoke_model.return_value = {
            "body": BytesIO(json.dumps(empty_response).encode())
        }

        handler(
            _s3_event(),
            None,
            s3_client=s3_client,
            textract_client=textract,
            bedrock_client=bedrock,
        )

        result = get_results(RESULTS_BUCKET, JOB_ID, s3_client=s3_client)
        assert result is not None
        assert result.status == JobStatus.COMPLETED
        assert result.dishes == []

    def test_partial_image_failure_stores_partial_result(self, aws_env, s3_client):
        textract = _mock_textract()

        dishes_json = json.dumps(
            [
                {"original_name": "Good Dish", "ingredients": []},
                {"original_name": "Bad Dish", "ingredients": []},
            ]
        )
        llm_response = {"content": [{"type": "text", "text": dishes_json}]}

        import base64

        fake_image = base64.b64encode(b"fake-png").decode()
        good_image_response = {"images": [fake_image]}

        call_count = [0]

        def invoke_model(**kwargs):
            body = json.loads(kwargs.get("body", "{}"))
            if "messages" in body:
                return {"body": BytesIO(json.dumps(llm_response).encode())}
            # Image gen: first succeeds, second fails
            call_count[0] += 1
            if call_count[0] == 1:
                return {"body": BytesIO(json.dumps(good_image_response).encode())}
            else:
                return {"body": BytesIO(json.dumps({"images": []}).encode())}

        bedrock = MagicMock()
        bedrock.invoke_model.side_effect = invoke_model

        handler(
            _s3_event(),
            None,
            s3_client=s3_client,
            textract_client=textract,
            bedrock_client=bedrock,
        )

        result = get_results(RESULTS_BUCKET, JOB_ID, s3_client=s3_client)
        assert result is not None
        assert result.status == JobStatus.PARTIAL
        assert len(result.dishes) == 2
        # One dish should have a real URL, the other a placeholder
        urls = [d.image_url for d in result.dishes]
        assert any("placeholder" in u for u in urls)
        assert any("placeholder" not in u for u in urls)
