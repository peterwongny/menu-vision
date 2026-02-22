"""Unit tests for the Status Lambda handler."""

import json
import os

import boto3
import pytest
from moto import mock_aws

from menu_vision.handlers.status import handler
from menu_vision.models import DishRecord, JobStatus, MenuResult
from menu_vision.storage import store_results

RESULTS_BUCKET = "test-results"
JOB_ID = "test-job-123"


def _api_event(job_id: str) -> dict:
    return {"pathParameters": {"jobId": job_id}}


@pytest.fixture
def aws_env(monkeypatch):
    monkeypatch.setenv("RESULTS_BUCKET", RESULTS_BUCKET)


@pytest.fixture
def s3_client():
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=RESULTS_BUCKET)
        yield client


class TestStatusHandler:
    def test_returns_200_with_completed_result(self, aws_env, s3_client):
        result = MenuResult(
            job_id=JOB_ID,
            status=JobStatus.COMPLETED,
            source_language="French",
            dishes=[
                DishRecord(
                    original_name="Boeuf Bourguignon",
                    translated_name="Beef Burgundy",
                    price="€24",
                )
            ],
        )
        store_results(RESULTS_BUCKET, JOB_ID, result, s3_client=s3_client)

        response = handler(_api_event(JOB_ID), None, s3_client=s3_client)

        assert response["statusCode"] == 200
        assert response["headers"]["Content-Type"] == "application/json"

        body = json.loads(response["body"])
        assert body["job_id"] == JOB_ID
        assert body["status"] == "completed"
        assert len(body["dishes"]) == 1
        assert body["dishes"][0]["original_name"] == "Boeuf Bourguignon"

    def test_returns_404_for_nonexistent_job(self, aws_env, s3_client):
        response = handler(_api_event("no-such-job"), None, s3_client=s3_client)

        assert response["statusCode"] == 404
        body = json.loads(response["body"])
        assert body["error"] == "Job not found"

    def test_returns_processing_status(self, aws_env, s3_client):
        result = MenuResult(job_id=JOB_ID, status=JobStatus.PROCESSING)
        store_results(RESULTS_BUCKET, JOB_ID, result, s3_client=s3_client)

        response = handler(_api_event(JOB_ID), None, s3_client=s3_client)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["status"] == "processing"
        assert body["dishes"] == []

    def test_returns_failed_status_with_error_message(self, aws_env, s3_client):
        result = MenuResult(
            job_id=JOB_ID,
            status=JobStatus.FAILED,
            error_message="OCR extraction failed",
        )
        store_results(RESULTS_BUCKET, JOB_ID, result, s3_client=s3_client)

        response = handler(_api_event(JOB_ID), None, s3_client=s3_client)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["status"] == "failed"
        assert body["error_message"] == "OCR extraction failed"

    def test_returns_500_on_missing_env_var(self, s3_client, monkeypatch):
        monkeypatch.delenv("RESULTS_BUCKET", raising=False)

        response = handler(_api_event(JOB_ID), None, s3_client=s3_client)

        assert response["statusCode"] == 500
        body = json.loads(response["body"])
        assert "error" in body

    def test_returns_500_on_missing_path_parameters(self, aws_env, s3_client):
        response = handler({}, None, s3_client=s3_client)

        assert response["statusCode"] == 500
        body = json.loads(response["body"])
        assert "error" in body
