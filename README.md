# Menu Vision

AI-powered menu translator that photographs a restaurant menu and returns each dish with an English translation, description, and AI-generated food image.

## Architecture

- **Frontend** — React + TypeScript SPA served via CloudFront
- **Backend** — Python Lambda functions behind API Gateway
- **Infra** — AWS CDK (Cognito, S3, DynamoDB, Lambda, API Gateway, CloudFront)

### Pipeline

1. User uploads a menu photo
2. Amazon Textract extracts text (OCR)
3. Claude (Bedrock) structures and translates dishes
4. Stability AI (Bedrock) generates a photo for each dish
5. Results stream incrementally to the frontend

## Project Structure

```
├── backend/          # Python Lambda handlers + core modules
│   ├── handlers/     # submit, process, status Lambda handlers
│   ├── models.py     # DishRecord, MenuResult, JobStatus
│   ├── ocr.py        # Textract integration
│   ├── llm.py        # Claude integration
│   ├── image_gen.py  # Stability AI image generation
│   └── storage.py    # S3 storage helpers
├── frontend/         # React + TypeScript + Vite
│   └── src/
├── infra/            # AWS CDK stack
├── tests/            # pytest unit + property-based tests
└── pyproject.toml
```

## Setup

### Backend

```bash
pip install -e ".[dev]"
python -m pytest tests/
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Deploy

```bash
cd infra
pip install -r requirements.txt
npx aws-cdk deploy
```

## Tech Stack

- Python 3.12, React 18, TypeScript, Vite
- AWS: Lambda, API Gateway, S3, CloudFront, Cognito, Textract, Bedrock
- Models: Claude Haiku 4.5 (text), Stability AI Stable Image Core (images)
- Testing: pytest, Hypothesis (property-based), Vitest, fast-check
