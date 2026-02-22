"""S3 storage module - stores and retrieves images and results."""

from __future__ import annotations

import json
from typing import Optional

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from backend.models import MenuResult

_S3_CONFIG = Config(signature_version="s3v4")


def _default_s3_client():
    return boto3.client("s3", config=_S3_CONFIG)


def store_image(
    bucket: str,
    job_id: str,
    dish_index: int,
    image_bytes: bytes,
    s3_client=None,
) -> str:
    """Stores a generated dish image in S3. Returns a pre-signed GET URL (1 hour expiry)."""
    if s3_client is None:
        s3_client = _default_s3_client()

    key = f"{job_id}/dish_{dish_index}.png"
    s3_client.put_object(
        Bucket=bucket,
        Key=key,
        Body=image_bytes,
        ContentType="image/png",
    )

    url = s3_client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=3600,
    )
    return url


def store_results(
    bucket: str,
    job_id: str,
    menu_result: MenuResult,
    s3_client=None,
) -> None:
    """Stores the final MenuResult JSON in S3."""
    if s3_client is None:
        s3_client = _default_s3_client()

    key = f"{job_id}/result.json"
    body = json.dumps(menu_result.to_json())
    s3_client.put_object(
        Bucket=bucket,
        Key=key,
        Body=body,
        ContentType="application/json",
    )


def get_results(
    bucket: str,
    job_id: str,
    s3_client=None,
) -> Optional[MenuResult]:
    """Retrieves MenuResult from S3. Returns None if not yet available."""
    if s3_client is None:
        s3_client = _default_s3_client()

    key = f"{job_id}/result.json"
    try:
        response = s3_client.get_object(Bucket=bucket, Key=key)
        data = json.loads(response["Body"].read())
        return MenuResult.from_json(data)
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "")
        if error_code in ("NoSuchKey", "404"):
            return None
        raise
