"""Request validation for API Gateway Lambda handlers."""

from __future__ import annotations

import json
import re

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _error_response(message: str) -> dict:
    """Return a 400 API Gateway response with a descriptive error."""
    return {
        "statusCode": 400,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"error": message}),
    }


def validate_submit_request(event: dict) -> dict | None:
    """Validate a POST /jobs submit request.

    Returns ``None`` if the request is valid, or a 400 API Gateway response
    dict if validation fails.
    """
    if not isinstance(event, dict):
        return _error_response("Invalid request: expected a JSON object")

    # Validate API Gateway structure – must have httpMethod or requestContext
    if "httpMethod" not in event and "requestContext" not in event:
        return _error_response(
            "Invalid request structure: not a valid API Gateway event"
        )

    # If a body is provided, Content-Type header should be present
    body = event.get("body")
    if body is not None and body != "":
        headers = event.get("headers") or {}
        # API Gateway may lowercase header keys
        content_type = headers.get("Content-Type") or headers.get("content-type")
        if not content_type:
            return _error_response(
                "Missing Content-Type header for request with body"
            )

    return None


def validate_status_request(event: dict) -> dict | None:
    """Validate a GET /jobs/{jobId} status request.

    Returns ``None`` if the request is valid, or a 400 API Gateway response
    dict if validation fails.
    """
    if not isinstance(event, dict):
        return _error_response("Invalid request: expected a JSON object")

    path_params = event.get("pathParameters")
    if path_params is None or not isinstance(path_params, dict):
        return _error_response("Missing path parameters")

    job_id = path_params.get("jobId")
    if job_id is None or not isinstance(job_id, str) or job_id.strip() == "":
        return _error_response("Missing or empty jobId path parameter")

    if not _UUID_RE.match(job_id):
        return _error_response(
            "Invalid jobId format: expected a UUID (e.g. 550e8400-e29b-41d4-a716-446655440000)"
        )

    return None
