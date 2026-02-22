"""Data models for Menu Vision: DishRecord, MenuResult, JobStatus, ProcessingJob."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class JobStatus(Enum):
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"  # Some dishes failed but others succeeded


@dataclass
class DishRecord:
    original_name: str
    translated_name: Optional[str] = None
    description: Optional[str] = None
    ingredients: list[str] = field(default_factory=list)
    price: Optional[str] = None
    image_url: Optional[str] = None

    def to_json(self) -> dict:
        return {
            "original_name": self.original_name,
            "translated_name": self.translated_name,
            "description": self.description,
            "ingredients": list(self.ingredients),
            "price": self.price,
            "image_url": self.image_url,
        }

    @classmethod
    def from_json(cls, data: dict) -> DishRecord:
        return cls(
            original_name=data["original_name"],
            translated_name=data.get("translated_name"),
            description=data.get("description"),
            ingredients=list(data.get("ingredients", [])),
            price=data.get("price"),
            image_url=data.get("image_url"),
        )


@dataclass
class MenuResult:
    job_id: str
    status: JobStatus
    source_language: Optional[str] = None
    dishes: list[DishRecord] = field(default_factory=list)
    error_message: Optional[str] = None

    def to_json(self) -> dict:
        return {
            "job_id": self.job_id,
            "status": self.status.value,
            "source_language": self.source_language,
            "dishes": [dish.to_json() for dish in self.dishes],
            "error_message": self.error_message,
        }

    @classmethod
    def from_json(cls, data: dict) -> MenuResult:
        return cls(
            job_id=data["job_id"],
            status=JobStatus(data["status"]),
            source_language=data.get("source_language"),
            dishes=[DishRecord.from_json(d) for d in data.get("dishes", [])],
            error_message=data.get("error_message"),
        )


@dataclass
class ProcessingJob:
    job_id: str
    image_bucket: str
    image_key: str

    def to_json(self) -> dict:
        return {
            "job_id": self.job_id,
            "image_bucket": self.image_bucket,
            "image_key": self.image_key,
        }

    @classmethod
    def from_json(cls, data: dict) -> ProcessingJob:
        return cls(
            job_id=data["job_id"],
            image_bucket=data["image_bucket"],
            image_key=data["image_key"],
        )
