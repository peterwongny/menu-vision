"""Status Lambda handler - returns job status and results."""

from __future__ import annotations

import json
import logging
import os

import boto3

from menu_vision.storage import get_results

logger = logging.getLogger(__name__)

_s3_client = None


def _get_s3_client():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client("s3")
    return _s3_client


def handler(event, context, s3_client=None) -> dict:
    """
    Returns job status and results when complete.
    """
    try:
        client = s3_client or _get_s3_client()
        results_bucket = os.environ["RESULTS_BUCKET"]

        job_id = event["pathParameters"]["jobId"]

        result = get_results(results_bucket, job_id, s3_client=client)

        if result is None:
            return {
                "statusCode": 404,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Headers": "Content-Type,Authorization",
                },
                "body": json.dumps({"error": "Job not found"}),
            }

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type,Authorization",
            },
            "body": json.dumps(result.to_json()),
        }

    except Exception as exc:
        logger.error("Status handler error: %s", exc)
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type,Authorization",
            },
            "body": json.dumps({"error": str(exc)}),
        }
