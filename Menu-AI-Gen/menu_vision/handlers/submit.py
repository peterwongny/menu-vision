"""Submit Lambda handler - creates a job and returns a pre-signed upload URL."""

from __future__ import annotations

import json
import os
import uuid

import boto3
from botocore.config import Config

from menu_vision.models import JobStatus, MenuResult
from menu_vision.storage import store_results

_s3_client = None


def _get_s3_client():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client(
            "s3",
            config=Config(signature_version="s3v4"),
        )
    return _s3_client


def handler(event, context, s3_client=None) -> dict:
    """
    Creates a new job. Generates a pre-signed S3 upload URL for the image.
    Returns: { "jobId": "<uuid>", "uploadUrl": "<pre-signed S3 PUT URL>" }
    """
    try:
        client = s3_client or _get_s3_client()
        upload_bucket = os.environ["UPLOAD_BUCKET"]
        results_bucket = os.environ["RESULTS_BUCKET"]

        job_id = str(uuid.uuid4())
        s3_key = f"{job_id}/menu_image"

        upload_url = client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": upload_bucket,
                "Key": s3_key,
            },
            ExpiresIn=900,
            HttpMethod="PUT",
        )

        initial_result = MenuResult(
            job_id=job_id,
            status=JobStatus.PROCESSING,
        )
        store_results(results_bucket, job_id, initial_result, s3_client=client)

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type,Authorization",
            },
            "body": json.dumps({"jobId": job_id, "uploadUrl": upload_url}),
        }
    except Exception as exc:
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type,Authorization",
            },
            "body": json.dumps({"error": str(exc)}),
        }
