"""Unit tests for the Submit Lambda handler."""

import json
import os

import boto3
import pytest
from moto import mock_aws

from backend.handlers.submit import handler
from backend.storage import get_results
from backend.models import JobStatus

UPLOAD_BUCKET = "test-uploads"
RESULTS_BUCKET = "test-results"


@pytest.fixture
def aws_env(monkeypatch):
    monkeypatch.setenv("UPLOAD_BUCKET", UPLOAD_BUCKET)
    monkeypatch.setenv("RESULTS_BUCKET", RESULTS_BUCKET)


@pytest.fixture
def s3_client():
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=UPLOAD_BUCKET)
        client.create_bucket(Bucket=RESULTS_BUCKET)
        yield client


class TestSubmitHandler:
    def test_returns_200_with_job_id_and_upload_url(self, aws_env, s3_client):
        response = handler({}, None, s3_client=s3_client)

        assert response["statusCode"] == 200
        assert response["headers"]["Content-Type"] == "application/json"

        body = json.loads(response["body"])
        assert "jobId" in body
        assert "uploadUrl" in body
        assert len(body["jobId"]) == 36  # UUID format
        assert "menu_image" in body["uploadUrl"]

    def test_writes_initial_processing_status(self, aws_env, s3_client):
        response = handler({}, None, s3_client=s3_client)
        body = json.loads(response["body"])
        job_id = body["jobId"]

        result = get_results(RESULTS_BUCKET, job_id, s3_client=s3_client)
        assert result is not None
        assert result.job_id == job_id
        assert result.status == JobStatus.PROCESSING
        assert result.dishes == []

    def test_presigned_url_contains_upload_bucket(self, aws_env, s3_client):
        response = handler({}, None, s3_client=s3_client)
        body = json.loads(response["body"])
        assert UPLOAD_BUCKET in body["uploadUrl"]

    def test_each_call_generates_unique_job_id(self, aws_env, s3_client):
        r1 = handler({}, None, s3_client=s3_client)
        r2 = handler({}, None, s3_client=s3_client)
        id1 = json.loads(r1["body"])["jobId"]
        id2 = json.loads(r2["body"])["jobId"]
        assert id1 != id2

    def test_returns_500_on_missing_env_vars(self, s3_client, monkeypatch):
        monkeypatch.delenv("UPLOAD_BUCKET", raising=False)
        monkeypatch.delenv("RESULTS_BUCKET", raising=False)

        response = handler({}, None, s3_client=s3_client)
        assert response["statusCode"] == 500
        body = json.loads(response["body"])
        assert "error" in body
