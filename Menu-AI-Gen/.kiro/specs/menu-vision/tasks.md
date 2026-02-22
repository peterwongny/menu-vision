# Implementation Plan: Menu Vision

## Overview

Build the core pipeline locally first (OCR → LLM → Image Gen), verify it works with real menu images, then wrap it in Lambda handlers and deploy the serverless infrastructure. Frontend is a mobile-first React app with Cognito auth.

Development order: Data models → Core pipeline modules → Local CLI → Lambda handlers → Infrastructure (CDK) → Frontend

## Tasks

- [x] 1. Set up project structure and data models
  - [x] 1.1 Create Python project structure with `menu_vision/` package, `pyproject.toml`, and dependencies (boto3, Pillow)
    - Create `menu_vision/__init__.py`, `menu_vision/models.py`, `menu_vision/ocr.py`, `menu_vision/llm.py`, `menu_vision/image_gen.py`, `menu_vision/pipeline.py`, `menu_vision/storage.py`
    - Add `tests/` directory with `conftest.py`
    - Install `hypothesis` for property-based testing, `pytest` for unit tests, `moto` for AWS mocking
    - _Requirements: 3.5, 6.3_

  - [x] 1.2 Implement data models (`DishRecord`, `MenuResult`, `JobStatus`, `ProcessingJob`) in `menu_vision/models.py`
    - Implement `to_json()` and `from_json()` class methods for serialization/deserialization
    - Use dataclasses as specified in the design
    - _Requirements: 3.5_

  - [x] 1.3 Write property test for DishRecord JSON round-trip
    - **Property 5: DishRecord JSON round-trip**
    - Generate random DishRecord instances with hypothesis, serialize to JSON, deserialize back, assert equality
    - **Validates: Requirements 3.5**

- [x] 2. Implement OCR module
  - [x] 2.1 Implement `extract_text()` in `menu_vision/ocr.py`
    - Call Amazon Textract `detect_document_text` API
    - Concatenate extracted text blocks into a single string
    - Raise `OCRExtractionError` if no text detected
    - _Requirements: 2.1, 2.2, 2.4_

  - [x] 2.2 Write unit tests for OCR module
    - Test with mocked Textract responses (successful extraction, empty result, API error)
    - Test that `OCRExtractionError` is raised when no text detected
    - _Requirements: 2.1, 2.4_

- [x] 3. Implement LLM menu structuring module
  - [x] 3.1 Implement `structure_menu()` in `menu_vision/llm.py`
    - Call Bedrock Claude via `invoke_model` API
    - Construct a prompt that instructs Claude to extract dish names, descriptions, ingredients, prices, and translate to English
    - Parse Claude's JSON response into a list of `DishRecord` objects
    - Mark unknown fields as `None` (not fabricated values)
    - Raise `LLMProcessingError` on failure
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 3.2 Write property test for LLM response parsing
    - **Property 3: LLM response parsing produces complete DishRecords**
    - Generate random valid JSON strings conforming to the LLM output schema, parse them, verify each DishRecord has a non-empty `original_name` and all other fields are either populated or explicitly None
    - **Validates: Requirements 3.1, 3.2**

  - [x] 3.3 Write property test for unknown field handling
    - **Property 4: Unknown fields are None, not fabricated**
    - Generate JSON responses with random null/absent fields, parse them, verify corresponding DishRecord fields are None or empty list
    - **Validates: Requirements 3.4**

- [x] 4. Implement image generation module
  - [x] 4.1 Implement `build_image_prompt()` and `generate_dish_image()` in `menu_vision/image_gen.py`
    - Build a photorealistic food photography prompt from dish name, description, and ingredients
    - Call Bedrock image model (configurable via `IMAGE_MODEL_ID` env var, default Titan v2)
    - Return PNG image bytes
    - Raise `ImageGenerationError` on failure
    - _Requirements: 4.1, 4.2_

  - [x] 4.2 Implement `generate_all_dish_images()` with parallel execution
    - Use `concurrent.futures.ThreadPoolExecutor` with configurable worker count (default 10)
    - Add retry with exponential backoff for `ThrottlingException`
    - Return list of `(dish_index, image_bytes | None)` — failed dishes return None
    - _Requirements: 4.1, 4.4, 7.1_

  - [x] 4.3 Write unit tests for image generation module
    - Test prompt construction with known dish data
    - Test parallel execution with mocked Bedrock (some succeed, some fail)
    - Test retry logic on throttling
    - _Requirements: 4.1, 4.4_

- [x] 5. Implement pipeline orchestrator and local CLI
  - [x] 5.1 Implement `run_pipeline()` in `menu_vision/pipeline.py`
    - Orchestrate: read image → OCR → LLM → parallel image gen → assemble MenuResult
    - Handle partial failures: if image gen fails for a dish, attach placeholder URL and continue
    - Monitor elapsed time for timeout handling (configurable threshold)
    - _Requirements: 6.3, 7.1, 7.3_

  - [x] 5.2 Implement local CLI entry point in `menu_vision/__main__.py`
    - Accept `--image` path and `--output` directory arguments
    - Run the pipeline and save results JSON + dish images to the output directory
    - Print summary to stdout
    - _Requirements: 6.3_

  - [x] 5.3 Write property test for partial failure resilience
    - **Property 7: Partial results on pipeline dish failure**
    - Generate random dish lists, simulate random image generation failures, verify all dishes are present in the result with either real or placeholder image URLs
    - **Validates: Requirements 7.1, 4.4**

- [x] 6. Checkpoint - Test pipeline locally
  - Download 3-4 sample menu images in different languages (French, Italian, Chinese, Spanish) from the web
  - Run the local CLI against each sample image
  - Verify OCR extraction, LLM structuring, and image generation work end-to-end
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Implement Lambda handlers and S3 storage
  - [x] 7.1 Implement S3 storage functions in `menu_vision/storage.py`
    - `store_image()`: upload PNG to S3, return pre-signed URL
    - `store_results()`: write MenuResult JSON to S3
    - `get_results()`: read MenuResult JSON from S3, return None if not found
    - _Requirements: 4.3, 6.4_

  - [x] 7.2 Implement Submit Lambda handler in `menu_vision/handlers/submit.py`
    - Generate jobId (UUID), create pre-signed S3 upload URL with constraints (15 min TTL, 10MB max, image content types only)
    - Write initial job status to S3
    - Return `{ jobId, uploadUrl }`
    - _Requirements: 6.1, 8.4_

  - [x] 7.3 Implement Processing Lambda handler in `menu_vision/handlers/process.py`
    - Triggered by S3 event notification
    - Extract bucket/key from event, read image from S3
    - Run the pipeline, store images and results to S3
    - Handle errors: write error status to S3 on failure
    - _Requirements: 6.2, 6.3, 7.1, 7.2, 7.3_

  - [x] 7.4 Implement Status Lambda handler in `menu_vision/handlers/status.py`
    - Read job results from S3 by jobId
    - Return job status and MenuResult if complete
    - _Requirements: 5.1_

  - [x] 7.5 Write unit tests for Lambda handlers
    - Test Submit handler returns valid jobId and pre-signed URL
    - Test Processing handler with mocked pipeline
    - Test Status handler with existing and non-existing jobs
    - _Requirements: 6.1, 6.2, 7.2, 7.4_

- [x] 8. Implement request validation
  - [x] 8.1 Implement request validation in `menu_vision/handlers/validation.py`
    - Validate content type, required fields, request structure
    - Return 400 with descriptive error for malformed requests
    - _Requirements: 7.4_

  - [x] 8.2 Write property test for malformed request validation
    - **Property 8: Malformed requests produce 400 errors**
    - Generate random invalid request payloads (missing fields, wrong content types), verify 400 response with descriptive error
    - **Validates: Requirements 7.4**

- [x] 9. Checkpoint - Ensure all backend tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Set up AWS infrastructure with CDK
  - [x] 10.1 Create CDK app in `infra/` directory
    - Define S3 buckets (uploads, images with 30-day lifecycle, results, frontend)
    - Define Lambda functions (Submit, Processing, Status) with appropriate IAM roles
    - Configure S3 event notification on uploads bucket to trigger Processing Lambda
    - Set Processing Lambda concurrency limit to 1
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 8.3_

  - [x] 10.2 Configure API Gateway with Cognito authorizer
    - Create REST API with `POST /jobs` and `GET /jobs/{jobId}` endpoints
    - Create Cognito User Pool with one user, Hosted UI domain
    - Attach Cognito authorizer to all API endpoints
    - Configure CORS, throttling (10 burst / 5 sustained)
    - _Requirements: 8.1, 8.2, 8.6, 8.7_

  - [x] 10.3 Configure CloudFront and frontend hosting
    - Create S3 bucket for frontend static site
    - Create CloudFront distribution with Origin Access Control
    - Configure CloudFront to serve frontend and proxy API requests
    - _Requirements: 6.5, 8.5_

  - [x] 10.4 Add AWS Budget alarm
    - Create $10/month budget with 80% and 100% email notifications
    - _Requirements: 8 (cost control)_

- [x] 11. Implement React frontend
  - [x] 11.1 Create React app with Vite, mobile-first layout
    - Set up project with `npm create vite@latest frontend -- --template react-ts`
    - Install dependencies: `aws-amplify` (for Cognito auth), `axios`
    - Configure Amplify Auth with Cognito User Pool settings
    - _Requirements: 8.7_

  - [x] 11.2 Implement auth flow and protected routes
    - Redirect to Cognito Hosted UI if no valid session
    - Store and refresh JWT tokens
    - Attach access token to all API requests
    - _Requirements: 8.1, 8.2, 8.7_

  - [x] 11.3 Implement image capture and upload page
    - Camera capture button (uses device camera on mobile) and file upload button
    - Client-side validation: file format (JPEG, PNG, WEBP) and size (max 10MB)
    - Request pre-signed URL from API, upload image directly to S3
    - Show upload progress
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

  - [x] 11.4 Implement results display page
    - Poll `GET /jobs/{jobId}` until status is completed/partial/failed
    - Show progress indicator while processing
    - Render dish cards in responsive grid: image, original name, translated name, description, ingredients, price
    - Omit fields that are null/unknown (no placeholder labels)
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [x] 11.5 Write property test for file validation
    - **Property 1: File format validation accepts only supported types**
    - Generate random file metadata (MIME types, sizes), verify validation accepts only JPEG/PNG/WEBP under 10MB
    - **Validates: Requirements 1.2, 1.3, 1.5**

  - [x] 11.6 Write property test for card rendering
    - **Property 6: Card rendering displays exactly non-null fields**
    - Generate random DishRecord objects, render cards, verify all non-null fields are present and null fields are omitted
    - **Validates: Requirements 5.1, 5.3**

- [x] 12. Final checkpoint - Full integration verification
  - Deploy infrastructure with CDK
  - Verify Cognito login flow on mobile
  - Test end-to-end: upload menu photo from phone → see translated dishes with images
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Development follows local-first approach: core pipeline works locally before Lambda deployment
- Backend is Python 3.12, frontend is React + TypeScript
- Property tests use `hypothesis` (Python) and `fast-check` (TypeScript)
- Each property test references a specific design document property
- Checkpoints ensure incremental validation at key milestones
