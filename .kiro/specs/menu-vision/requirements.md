# Requirements Document

## Introduction

Menu Vision is an AI-powered web application that helps users understand foreign-language restaurant menus. The user photographs a menu, and the system extracts text via OCR, structures the content using an LLM, generates realistic images of each dish, and presents everything in a clean, translated interface. The application is hosted on AWS using a serverless architecture optimized for single-user, low-cost operation.

## Glossary

- **Menu_Image**: A photograph of a physical restaurant menu uploaded by the user
- **OCR_Service**: The optical character recognition component that extracts text from a Menu_Image
- **LLM_Service**: The large language model component that interprets extracted text and structures it into dish data
- **Image_Generator**: The AI image generation component that creates visual representations of dishes
- **Dish_Record**: A structured data object containing a dish name, translated name, description, ingredients list, price, and generated image URL
- **Menu_Result**: The complete processed output containing all Dish_Records extracted from a single Menu_Image
- **Pipeline**: The sequential processing chain: OCR → LLM extraction → Image generation
- **Frontend**: The web-based user interface that captures menu photos and displays Menu_Results
- **API_Gateway**: The AWS API Gateway endpoint that receives requests from the Frontend
- **Processing_Lambda**: The AWS Lambda function(s) that orchestrate the Pipeline

## Requirements

### Requirement 1: Menu Image Capture and Upload

**User Story:** As a user, I want to capture or upload a photo of a restaurant menu, so that the system can process it and help me understand the dishes.

#### Acceptance Criteria

1. WHEN a user opens the application, THE Frontend SHALL display an interface for capturing a new photo or uploading an existing image
2. WHEN a user captures or selects a Menu_Image, THE Frontend SHALL validate that the file is a supported image format (JPEG, PNG, WEBP)
3. IF a user selects an unsupported file format, THEN THE Frontend SHALL display a descriptive error message indicating the supported formats
4. WHEN a valid Menu_Image is selected, THE Frontend SHALL request a pre-signed upload URL from the API_Gateway and upload the image directly to S3
5. IF the Menu_Image exceeds 10 MB in size, THEN THE Frontend SHALL display an error message indicating the maximum allowed file size

### Requirement 2: Text Extraction via OCR

**User Story:** As a user, I want the system to extract text from my menu photo, so that the content can be interpreted regardless of the language.

#### Acceptance Criteria

1. WHEN the Processing_Lambda receives a Menu_Image, THE OCR_Service SHALL extract all visible text from the image
2. THE OCR_Service SHALL support text extraction in at least English, French, Italian, Spanish, and Chinese
3. WHEN the OCR_Service completes extraction, THE Processing_Lambda SHALL pass the raw extracted text to the LLM_Service
4. IF the OCR_Service fails to extract any text from the Menu_Image, THEN THE Processing_Lambda SHALL return an error indicating that no text was detected

### Requirement 3: Menu Understanding and Structuring via LLM

**User Story:** As a user, I want the system to understand the extracted menu text and organize it into structured dish information, so that I can see dish names, descriptions, ingredients, and prices clearly.

#### Acceptance Criteria

1. WHEN the LLM_Service receives raw extracted text, THE LLM_Service SHALL identify individual menu items and produce a list of Dish_Records
2. THE LLM_Service SHALL populate each Dish_Record with the original dish name, a translated dish name in English, a description, an ingredients list, and a price
3. WHEN the original menu text is not in English, THE LLM_Service SHALL translate the dish name and description into English
4. IF the LLM_Service cannot determine a field value from the extracted text, THEN THE LLM_Service SHALL mark that field as unknown rather than guessing
5. THE LLM_Service SHALL produce a structured JSON output conforming to the Dish_Record schema

### Requirement 4: Dish Image Generation

**User Story:** As a user, I want to see AI-generated images of each dish, so that I can visually understand what I am ordering before making a decision.

#### Acceptance Criteria

1. WHEN a Dish_Record is produced, THE Image_Generator SHALL create a photorealistic image based on the dish name, description, and ingredients
2. THE Image_Generator SHALL produce images that are faithful to the menu description and ingredients listed in the Dish_Record
3. WHEN the Image_Generator completes image creation, THE Processing_Lambda SHALL store the image in an S3 bucket and attach the URL to the corresponding Dish_Record
4. IF the Image_Generator fails to produce an image for a dish, THEN THE Processing_Lambda SHALL attach a placeholder image URL to the Dish_Record and continue processing remaining dishes

### Requirement 5: Results Display

**User Story:** As a user, I want to see all processed dishes displayed in a clear, formatted layout, so that I can browse and understand the entire menu at a glance.

#### Acceptance Criteria

1. WHEN the Frontend receives a Menu_Result, THE Frontend SHALL display each Dish_Record as a card containing the generated image, original name, translated name, description, ingredients, and price
2. WHILE the Pipeline is processing, THE Frontend SHALL display a progress indicator to the user
3. WHEN a Dish_Record has a field marked as unknown, THE Frontend SHALL omit that field from the card rather than displaying a placeholder label
4. THE Frontend SHALL arrange Dish_Record cards in a responsive grid layout that adapts to the device screen size

### Requirement 6: Serverless AWS Architecture

**User Story:** As a single user, I want the application hosted on AWS with a serverless architecture, so that I only pay for what I use and keep costs minimal.

#### Acceptance Criteria

1. THE API_Gateway SHALL expose a REST endpoint that returns a pre-signed S3 upload URL and job identifier to the Frontend
2. WHEN the image is uploaded to S3, THE S3 bucket SHALL trigger the Processing_Lambda to execute the Pipeline
3. THE Processing_Lambda SHALL orchestrate the Pipeline steps sequentially: OCR extraction, LLM structuring, and image generation
4. THE Processing_Lambda SHALL store generated images in an S3 bucket configured with a lifecycle policy to delete objects after 30 days
5. THE Frontend SHALL be deployed as a static site hosted on S3 with CloudFront distribution

### Requirement 7: Error Handling and Resilience

**User Story:** As a user, I want the system to handle errors gracefully at each stage of processing, so that partial failures do not prevent me from seeing available results.

#### Acceptance Criteria

1. IF any single step in the Pipeline fails for a specific dish, THEN THE Processing_Lambda SHALL continue processing the remaining dishes and return partial results
2. IF the entire Pipeline fails, THEN THE API_Gateway SHALL return a structured error response with a descriptive message
3. WHEN the Processing_Lambda encounters a timeout, THE Processing_Lambda SHALL return any results completed before the timeout occurred
4. IF the API_Gateway receives a malformed request, THEN THE API_Gateway SHALL return a 400 status code with a descriptive validation error message

### Requirement 8: Security and Cost Control

**User Story:** As the sole user, I want the system to prevent unauthorized access and cap costs, so that I do not receive unexpected AWS bills.

#### Acceptance Criteria

1. THE API_Gateway SHALL require a valid Cognito JWT token on all endpoints
2. IF a request is received without a valid JWT token, THEN THE API_Gateway SHALL return a 401 status code
3. THE Processing_Lambda SHALL have a reserved concurrency limit of 1 to prevent concurrent pipeline executions
4. THE Submit_Lambda SHALL generate pre-signed upload URLs with a maximum TTL of 15 minutes and a maximum content length of 10 MB
5. THE S3 buckets SHALL have public access blocked and serve content only through pre-signed URLs or CloudFront with Origin Access Control
6. THE API_Gateway SHALL enforce throttling limits of 10 requests per second burst and 5 requests per second sustained
7. WHEN a user opens the application without a valid session, THE Frontend SHALL redirect to the Cognito Hosted UI login page
