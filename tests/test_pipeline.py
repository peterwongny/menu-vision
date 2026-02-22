"""Unit tests for the pipeline orchestrator."""

from unittest.mock import MagicMock, patch
import pytest

from backend.models import DishRecord, JobStatus, MenuResult
from backend.ocr import OCRExtractionError
from backend.llm import LLMProcessingError
from backend.pipeline import PLACEHOLDER_IMAGE_URL, run_pipeline


def _make_dishes(n: int) -> list[DishRecord]:
    return [DishRecord(original_name=f"Dish {i}") for i in range(n)]


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestRunPipelineSuccess:
    def test_completed_when_all_images_succeed(self, tmp_path):
        img_file = tmp_path / "menu.jpg"
        img_file.write_bytes(b"fake-image")

        dishes = _make_dishes(2)
        image_results = [(0, b"png0"), (1, b"png1")]

        with (
            patch("backend.pipeline.extract_text", return_value="raw text"),
            patch("backend.pipeline.structure_menu", return_value=dishes),
            patch("backend.pipeline.generate_all_dish_images", return_value=image_results),
        ):
            result = run_pipeline(str(img_file))

        assert result.status == JobStatus.COMPLETED
        assert len(result.dishes) == 2
        assert result.error_message is None
        for dish in result.dishes:
            assert dish.image_url.startswith("generated://")

    def test_accepts_image_bytes_directly(self):
        dishes = _make_dishes(1)
        image_results = [(0, b"png0")]

        with (
            patch("backend.pipeline.extract_text", return_value="raw text"),
            patch("backend.pipeline.structure_menu", return_value=dishes),
            patch("backend.pipeline.generate_all_dish_images", return_value=image_results),
        ):
            result = run_pipeline(image_bytes=b"fake-image")

        assert result.status == JobStatus.COMPLETED
        assert len(result.dishes) == 1

    def test_empty_dish_list_returns_completed(self, tmp_path):
        img_file = tmp_path / "menu.jpg"
        img_file.write_bytes(b"fake-image")

        with (
            patch("backend.pipeline.extract_text", return_value="raw text"),
            patch("backend.pipeline.structure_menu", return_value=[]),
        ):
            result = run_pipeline(str(img_file))

        assert result.status == JobStatus.COMPLETED
        assert result.dishes == []


# ---------------------------------------------------------------------------
# Partial failures
# ---------------------------------------------------------------------------

class TestRunPipelinePartial:
    def test_partial_when_some_images_fail(self, tmp_path):
        img_file = tmp_path / "menu.jpg"
        img_file.write_bytes(b"fake-image")

        dishes = _make_dishes(3)
        image_results = [(0, b"png0"), (1, None), (2, b"png2")]

        with (
            patch("backend.pipeline.extract_text", return_value="raw text"),
            patch("backend.pipeline.structure_menu", return_value=dishes),
            patch("backend.pipeline.generate_all_dish_images", return_value=image_results),
        ):
            result = run_pipeline(str(img_file))

        assert result.status == JobStatus.PARTIAL
        assert len(result.dishes) == 3
        assert result.dishes[0].image_url == "generated://dish_0.png"
        assert result.dishes[1].image_url == PLACEHOLDER_IMAGE_URL
        assert result.dishes[2].image_url == "generated://dish_2.png"

    def test_partial_when_all_images_fail(self, tmp_path):
        img_file = tmp_path / "menu.jpg"
        img_file.write_bytes(b"fake-image")

        dishes = _make_dishes(2)
        image_results = [(0, None), (1, None)]

        with (
            patch("backend.pipeline.extract_text", return_value="raw text"),
            patch("backend.pipeline.structure_menu", return_value=dishes),
            patch("backend.pipeline.generate_all_dish_images", return_value=image_results),
        ):
            result = run_pipeline(str(img_file))

        assert result.status == JobStatus.PARTIAL
        assert all(d.image_url == PLACEHOLDER_IMAGE_URL for d in result.dishes)


# ---------------------------------------------------------------------------
# OCR / LLM failures → FAILED
# ---------------------------------------------------------------------------

class TestRunPipelineFailed:
    def test_failed_on_ocr_error(self, tmp_path):
        img_file = tmp_path / "menu.jpg"
        img_file.write_bytes(b"fake-image")

        with patch(
            "backend.pipeline.extract_text",
            side_effect=OCRExtractionError("no text"),
        ):
            result = run_pipeline(str(img_file))

        assert result.status == JobStatus.FAILED
        assert "OCR extraction failed" in result.error_message

    def test_failed_on_llm_error(self, tmp_path):
        img_file = tmp_path / "menu.jpg"
        img_file.write_bytes(b"fake-image")

        with (
            patch("backend.pipeline.extract_text", return_value="raw text"),
            patch(
                "backend.pipeline.structure_menu",
                side_effect=LLMProcessingError("bad json"),
            ),
        ):
            result = run_pipeline(str(img_file))

        assert result.status == JobStatus.FAILED
        assert "LLM processing failed" in result.error_message

    def test_failed_when_no_image_source(self):
        result = run_pipeline()
        assert result.status == JobStatus.FAILED
        assert "image_path or image_bytes" in result.error_message

    def test_failed_on_file_read_error(self):
        result = run_pipeline("/nonexistent/path/menu.jpg")
        assert result.status == JobStatus.FAILED
        assert "Failed to read image file" in result.error_message


# ---------------------------------------------------------------------------
# Timeout handling
# ---------------------------------------------------------------------------

class TestRunPipelineTimeout:
    def test_timeout_before_image_gen(self, tmp_path):
        """If elapsed time exceeds threshold before image gen, return PARTIAL."""
        img_file = tmp_path / "menu.jpg"
        img_file.write_bytes(b"fake-image")

        dishes = _make_dishes(2)

        def slow_extract(image_bytes, textract_client=None):
            return "raw text"

        with (
            patch("backend.pipeline.extract_text", side_effect=slow_extract),
            patch("backend.pipeline.structure_menu", return_value=dishes),
            patch("backend.pipeline.time") as mock_time,
        ):
            # Simulate: start=0, after OCR+LLM=800 (past 720 threshold)
            mock_time.monotonic.side_effect = [0.0, 800.0]
            result = run_pipeline(str(img_file), timeout_threshold=720)

        assert result.status == JobStatus.PARTIAL
        assert all(d.image_url == PLACEHOLDER_IMAGE_URL for d in result.dishes)
        assert "Timeout" in result.error_message


# ---------------------------------------------------------------------------
# Job ID generation
# ---------------------------------------------------------------------------

class TestRunPipelineJobId:
    def test_generates_unique_job_ids(self, tmp_path):
        img_file = tmp_path / "menu.jpg"
        img_file.write_bytes(b"fake-image")

        with (
            patch("backend.pipeline.extract_text", return_value="raw text"),
            patch("backend.pipeline.structure_menu", return_value=[]),
        ):
            r1 = run_pipeline(str(img_file))
            r2 = run_pipeline(str(img_file))

        assert r1.job_id != r2.job_id
        assert len(r1.job_id) == 36  # UUID format


# ---------------------------------------------------------------------------
# Dependency injection
# ---------------------------------------------------------------------------

class TestRunPipelineDI:
    def test_passes_clients_to_modules(self):
        mock_textract = MagicMock()
        mock_bedrock = MagicMock()
        dishes = _make_dishes(1)
        image_results = [(0, b"png0")]

        with (
            patch("backend.pipeline.extract_text", return_value="raw text") as mock_ocr,
            patch("backend.pipeline.structure_menu", return_value=dishes) as mock_llm,
            patch("backend.pipeline.generate_all_dish_images", return_value=image_results) as mock_img,
        ):
            run_pipeline(
                image_bytes=b"fake",
                textract_client=mock_textract,
                bedrock_client=mock_bedrock,
            )

        mock_ocr.assert_called_once_with(b"fake", textract_client=mock_textract)
        mock_llm.assert_called_once_with("raw text", bedrock_client=mock_bedrock)
        mock_img.assert_called_once_with(dishes, bedrock_client=mock_bedrock)
