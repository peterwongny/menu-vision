"""Unit tests for data models."""

from backend.models import DishRecord, MenuResult, JobStatus, ProcessingJob


class TestDishRecord:
    def test_to_json(self):
        dish = DishRecord(
            original_name="Boeuf Bourguignon",
            translated_name="Beef Burgundy",
            description="Slow-braised beef in red wine",
            ingredients=["beef", "red wine", "carrots"],
            price="€24.50",
            image_url="https://example.com/dish.png",
        )
        result = dish.to_json()
        assert result == {
            "original_name": "Boeuf Bourguignon",
            "translated_name": "Beef Burgundy",
            "description": "Slow-braised beef in red wine",
            "ingredients": ["beef", "red wine", "carrots"],
            "price": "€24.50",
            "image_url": "https://example.com/dish.png",
        }

    def test_from_json(self):
        data = {
            "original_name": "Ratatouille",
            "translated_name": None,
            "description": "Provençal vegetable stew",
            "ingredients": ["eggplant", "zucchini"],
            "price": "€18",
            "image_url": None,
        }
        dish = DishRecord.from_json(data)
        assert dish.original_name == "Ratatouille"
        assert dish.translated_name is None
        assert dish.ingredients == ["eggplant", "zucchini"]
        assert dish.image_url is None

    def test_from_json_missing_optional_fields(self):
        data = {"original_name": "Soup"}
        dish = DishRecord.from_json(data)
        assert dish.original_name == "Soup"
        assert dish.translated_name is None
        assert dish.description is None
        assert dish.ingredients == []
        assert dish.price is None
        assert dish.image_url is None

    def test_round_trip(self):
        dish = DishRecord(
            original_name="Crème Brûlée",
            translated_name="Burnt Cream",
            description="Custard with caramelized sugar",
            ingredients=["cream", "sugar", "vanilla", "eggs"],
            price="€12",
            image_url="https://example.com/creme.png",
        )
        assert DishRecord.from_json(dish.to_json()) == dish

    def test_ingredients_list_is_copied(self):
        ingredients = ["a", "b"]
        dish = DishRecord(original_name="Test", ingredients=ingredients)
        json_data = dish.to_json()
        json_data["ingredients"].append("c")
        assert dish.ingredients == ["a", "b"]


class TestMenuResult:
    def test_to_json_serializes_status_and_dishes(self):
        result = MenuResult(
            job_id="job-1",
            status=JobStatus.COMPLETED,
            source_language="French",
            dishes=[DishRecord(original_name="Soup")],
        )
        data = result.to_json()
        assert data["status"] == "completed"
        assert len(data["dishes"]) == 1
        assert data["dishes"][0]["original_name"] == "Soup"

    def test_from_json_deserializes_status_and_dishes(self):
        data = {
            "job_id": "job-2",
            "status": "partial",
            "source_language": "Italian",
            "dishes": [{"original_name": "Pasta", "ingredients": ["flour"]}],
            "error_message": None,
        }
        result = MenuResult.from_json(data)
        assert result.status == JobStatus.PARTIAL
        assert len(result.dishes) == 1
        assert result.dishes[0].original_name == "Pasta"

    def test_round_trip(self):
        result = MenuResult(
            job_id="job-3",
            status=JobStatus.FAILED,
            source_language=None,
            dishes=[],
            error_message="OCR failed",
        )
        assert MenuResult.from_json(result.to_json()) == result

    def test_from_json_missing_optional_fields(self):
        data = {"job_id": "job-4", "status": "processing"}
        result = MenuResult.from_json(data)
        assert result.source_language is None
        assert result.dishes == []
        assert result.error_message is None


class TestProcessingJob:
    def test_to_json(self):
        job = ProcessingJob(job_id="j1", image_bucket="bucket", image_key="key.jpg")
        assert job.to_json() == {
            "job_id": "j1",
            "image_bucket": "bucket",
            "image_key": "key.jpg",
        }

    def test_from_json(self):
        data = {"job_id": "j2", "image_bucket": "b", "image_key": "k.png"}
        job = ProcessingJob.from_json(data)
        assert job.job_id == "j2"
        assert job.image_bucket == "b"

    def test_round_trip(self):
        job = ProcessingJob(job_id="j3", image_bucket="bkt", image_key="img.webp")
        assert ProcessingJob.from_json(job.to_json()) == job


class TestJobStatus:
    def test_all_values(self):
        assert JobStatus.PROCESSING.value == "processing"
        assert JobStatus.COMPLETED.value == "completed"
        assert JobStatus.FAILED.value == "failed"
        assert JobStatus.PARTIAL.value == "partial"
