"""Unit tests for S3 storage module."""

import json

import boto3
import pytest
from moto import mock_aws

from menu_vision.models import DishRecord, JobStatus, MenuResult
from menu_vision.storage import get_results, store_image, store_results

BUCKET = "test-bucket"
JOB_ID = "job-123"


@pytest.fixture
def s3_client():
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET)
        yield client


def _sample_menu_result() -> MenuResult:
    return MenuResult(
        job_id=JOB_ID,
        status=JobStatus.COMPLETED,
        source_language="French",
        dishes=[
            DishRecord(
                original_name="Boeuf Bourguignon",
                translated_name="Beef Burgundy",
                description="Slow-braised beef in red wine",
                ingredients=["beef", "red wine", "carrots"],
                price="€24.50",
                image_url=None,
            ),
        ],
    )


class TestStoreImage:
    def test_uploads_png_and_returns_presigned_url(self, s3_client):
        image_bytes = b"\x89PNG\r\n\x1a\nfake-image-data"
        url = store_image(BUCKET, JOB_ID, 0, image_bytes, s3_client=s3_client)

        assert "dish_0.png" in url
        assert JOB_ID in url

        # Verify the object was actually stored
        obj = s3_client.get_object(Bucket=BUCKET, Key=f"{JOB_ID}/dish_0.png")
        assert obj["Body"].read() == image_bytes
        assert obj["ContentType"] == "image/png"

    def test_different_dish_indices(self, s3_client):
        for i in range(3):
            url = store_image(BUCKET, JOB_ID, i, b"img", s3_client=s3_client)
            assert f"dish_{i}.png" in url


class TestStoreResults:
    def test_stores_menu_result_json(self, s3_client):
        result = _sample_menu_result()
        store_results(BUCKET, JOB_ID, result, s3_client=s3_client)

        obj = s3_client.get_object(Bucket=BUCKET, Key=f"{JOB_ID}/result.json")
        data = json.loads(obj["Body"].read())
        assert data["job_id"] == JOB_ID
        assert data["status"] == "completed"
        assert len(data["dishes"]) == 1
        assert data["dishes"][0]["original_name"] == "Boeuf Bourguignon"
        assert obj["ContentType"] == "application/json"


class TestGetResults:
    def test_retrieves_stored_result(self, s3_client):
        original = _sample_menu_result()
        store_results(BUCKET, JOB_ID, original, s3_client=s3_client)

        retrieved = get_results(BUCKET, JOB_ID, s3_client=s3_client)
        assert retrieved is not None
        assert retrieved.job_id == original.job_id
        assert retrieved.status == original.status
        assert len(retrieved.dishes) == len(original.dishes)
        assert retrieved.dishes[0].original_name == "Boeuf Bourguignon"

    def test_returns_none_when_not_found(self, s3_client):
        result = get_results(BUCKET, "nonexistent-job", s3_client=s3_client)
        assert result is None
