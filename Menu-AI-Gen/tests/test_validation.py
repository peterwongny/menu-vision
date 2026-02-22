"""Unit tests for request validation."""

import json

from menu_vision.handlers.validation import (
    validate_status_request,
    validate_submit_request,
)


class TestValidateSubmitRequest:
    def test_valid_request_with_http_method(self):
        event = {"httpMethod": "POST", "body": None}
        assert validate_submit_request(event) is None

    def test_valid_request_with_request_context(self):
        event = {"requestContext": {"stage": "prod"}, "body": None}
        assert validate_submit_request(event) is None

    def test_valid_request_with_body_and_content_type(self):
        event = {
            "httpMethod": "POST",
            "headers": {"Content-Type": "application/json"},
            "body": '{"key": "value"}',
        }
        assert validate_submit_request(event) is None

    def test_valid_request_with_lowercase_content_type(self):
        event = {
            "httpMethod": "POST",
            "headers": {"content-type": "application/json"},
            "body": '{"key": "value"}',
        }
        assert validate_submit_request(event) is None

    def test_invalid_not_api_gateway_event(self):
        event = {"someField": "value"}
        resp = validate_submit_request(event)
        assert resp is not None
        assert resp["statusCode"] == 400
        body = json.loads(resp["body"])
        assert "API Gateway" in body["error"]

    def test_invalid_body_without_content_type(self):
        event = {"httpMethod": "POST", "body": '{"key": "value"}'}
        resp = validate_submit_request(event)
        assert resp is not None
        assert resp["statusCode"] == 400
        body = json.loads(resp["body"])
        assert "Content-Type" in body["error"]

    def test_invalid_body_with_empty_headers(self):
        event = {"httpMethod": "POST", "headers": {}, "body": "data"}
        resp = validate_submit_request(event)
        assert resp is not None
        assert resp["statusCode"] == 400

    def test_valid_request_with_empty_body(self):
        event = {"httpMethod": "POST", "body": ""}
        assert validate_submit_request(event) is None

    def test_valid_request_with_none_body(self):
        event = {"httpMethod": "POST", "body": None}
        assert validate_submit_request(event) is None

    def test_invalid_non_dict_input(self):
        resp = validate_submit_request("not a dict")
        assert resp is not None
        assert resp["statusCode"] == 400


class TestValidateStatusRequest:
    def test_valid_uuid_job_id(self):
        event = {"pathParameters": {"jobId": "550e8400-e29b-41d4-a716-446655440000"}}
        assert validate_status_request(event) is None

    def test_missing_path_parameters(self):
        resp = validate_status_request({})
        assert resp is not None
        assert resp["statusCode"] == 400
        body = json.loads(resp["body"])
        assert "path parameters" in body["error"].lower()

    def test_null_path_parameters(self):
        resp = validate_status_request({"pathParameters": None})
        assert resp is not None
        assert resp["statusCode"] == 400

    def test_missing_job_id(self):
        resp = validate_status_request({"pathParameters": {}})
        assert resp is not None
        assert resp["statusCode"] == 400
        body = json.loads(resp["body"])
        assert "jobId" in body["error"]

    def test_empty_job_id(self):
        resp = validate_status_request({"pathParameters": {"jobId": ""}})
        assert resp is not None
        assert resp["statusCode"] == 400

    def test_whitespace_job_id(self):
        resp = validate_status_request({"pathParameters": {"jobId": "   "}})
        assert resp is not None
        assert resp["statusCode"] == 400

    def test_invalid_job_id_format(self):
        resp = validate_status_request({"pathParameters": {"jobId": "not-a-uuid"}})
        assert resp is not None
        assert resp["statusCode"] == 400
        body = json.loads(resp["body"])
        assert "UUID" in body["error"]

    def test_invalid_non_dict_input(self):
        resp = validate_status_request(42)
        assert resp is not None
        assert resp["statusCode"] == 400

    def test_valid_uppercase_uuid(self):
        event = {"pathParameters": {"jobId": "550E8400-E29B-41D4-A716-446655440000"}}
        assert validate_status_request(event) is None

    def test_response_format(self):
        resp = validate_status_request({})
        assert resp["headers"] == {"Content-Type": "application/json"}
        body = json.loads(resp["body"])
        assert "error" in body
        assert isinstance(body["error"], str)
        assert len(body["error"]) > 0
