# Feature: menu-vision, Property 8: Malformed requests produce 400 errors
"""Property-based tests for malformed request validation.

**Validates: Requirements 7.4**
"""

from __future__ import annotations

import json

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from backend.handlers.validation import (
    validate_submit_request,
    validate_status_request,
)


# ---------------------------------------------------------------------------
# Strategies for invalid submit requests
# ---------------------------------------------------------------------------

# Events that are dicts but lack both httpMethod and requestContext
_invalid_api_gateway_events = st.fixed_dictionaries(
    {},
    optional={
        "body": st.one_of(st.none(), st.text()),
        "headers": st.one_of(st.none(), st.dictionaries(st.text(), st.text())),
        "queryStringParameters": st.one_of(st.none(), st.dictionaries(st.text(), st.text())),
    },
).filter(lambda d: "httpMethod" not in d and "requestContext" not in d)

# Events that have a non-empty body but no Content-Type header
_missing_content_type_events = st.fixed_dictionaries(
    {
        "httpMethod": st.just("POST"),
        "body": st.text(min_size=1),
    },
    optional={
        "headers": st.one_of(
            st.none(),
            st.just({}),
            # headers with keys that are NOT Content-Type / content-type
            st.dictionaries(
                st.text().filter(lambda k: k.lower() != "content-type"),
                st.text(),
                max_size=3,
            ),
        ),
    },
)


# ---------------------------------------------------------------------------
# Strategies for invalid status requests
# ---------------------------------------------------------------------------

# Events with missing or null pathParameters
_missing_path_params_events = st.one_of(
    st.fixed_dictionaries({}),  # no pathParameters key
    st.fixed_dictionaries({"pathParameters": st.none()}),  # null
    st.fixed_dictionaries({"pathParameters": st.just("not-a-dict")}),  # wrong type
)

# Events with missing or empty jobId
_missing_job_id_events = st.one_of(
    st.fixed_dictionaries({"pathParameters": st.just({})}),  # no jobId key
    st.fixed_dictionaries({"pathParameters": st.fixed_dictionaries({"jobId": st.none()})}),
    st.fixed_dictionaries({"pathParameters": st.fixed_dictionaries({"jobId": st.just("")})}),
    st.fixed_dictionaries(
        {"pathParameters": st.fixed_dictionaries({"jobId": st.from_regex(r"^\s+$", fullmatch=True)})}
    ),
)

# Events with a jobId that is a non-empty string but NOT a valid UUID
_non_uuid_job_id = st.text(min_size=1).filter(
    lambda s: s.strip() != ""
    and not __import__("re").match(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        s,
        __import__("re").IGNORECASE,
    )
)

_invalid_uuid_events = st.fixed_dictionaries(
    {"pathParameters": st.fixed_dictionaries({"jobId": _non_uuid_job_id})}
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _assert_400_with_message(response: dict) -> None:
    """Assert the response is a 400 with a non-empty error message."""
    assert response is not None, "Expected a 400 error response, got None (valid)"
    assert response["statusCode"] == 400
    body = json.loads(response["body"])
    assert "error" in body
    assert isinstance(body["error"], str)
    assert len(body["error"]) > 0


# ---------------------------------------------------------------------------
# Property tests – submit validation
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(event=_invalid_api_gateway_events)
def test_submit_rejects_non_api_gateway_events(event: dict):
    """**Validates: Requirements 7.4**

    Events missing both httpMethod and requestContext must produce 400.
    """
    resp = validate_submit_request(event)
    _assert_400_with_message(resp)


@settings(max_examples=100)
@given(event=_missing_content_type_events)
def test_submit_rejects_body_without_content_type(event: dict):
    """**Validates: Requirements 7.4**

    Events with a non-empty body but no Content-Type header must produce 400.
    """
    resp = validate_submit_request(event)
    _assert_400_with_message(resp)


# ---------------------------------------------------------------------------
# Property tests – status validation
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(event=_missing_path_params_events)
def test_status_rejects_missing_path_parameters(event: dict):
    """**Validates: Requirements 7.4**

    Events with missing or null pathParameters must produce 400.
    """
    resp = validate_status_request(event)
    _assert_400_with_message(resp)


@settings(max_examples=100)
@given(event=_missing_job_id_events)
def test_status_rejects_missing_or_empty_job_id(event: dict):
    """**Validates: Requirements 7.4**

    Events with missing, null, or whitespace-only jobId must produce 400.
    """
    resp = validate_status_request(event)
    _assert_400_with_message(resp)


@settings(max_examples=100)
@given(event=_invalid_uuid_events)
def test_status_rejects_non_uuid_job_id(event: dict):
    """**Validates: Requirements 7.4**

    Events with a jobId that is not a valid UUID must produce 400.
    """
    resp = validate_status_request(event)
    _assert_400_with_message(resp)
