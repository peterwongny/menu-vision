"""Unit tests for the local CLI entry point (menu_vision/__main__.py)."""

from unittest.mock import patch
import json
import os
import sys

import pytest

from menu_vision.__main__ import main
from menu_vision.models import DishRecord, JobStatus, MenuResult


def _make_result(dishes=None, status=JobStatus.COMPLETED, error_message=None):
    return MenuResult(
        job_id="test-job-123",
        status=status,
        dishes=dishes or [],
        error_message=error_message,
    )


class TestCLIArgParsing:
    def test_missing_image_arg_exits(self):
        with patch("sys.argv", ["menu_vision"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 2  # argparse error

    def test_nonexistent_image_exits(self, tmp_path):
        fake_path = str(tmp_path / "nope.jpg")
        with patch("sys.argv", ["menu_vision", "--image", fake_path]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1


class TestCLIOutputs:
    def test_saves_result_json(self, tmp_path):
        img = tmp_path / "menu.jpg"
        img.write_bytes(b"fake")
        out_dir = tmp_path / "out"

        dishes = [
            DishRecord(original_name="Pasta", translated_name="Pasta", price="$12"),
            DishRecord(original_name="Soupe", translated_name="Soup"),
        ]
        result = _make_result(dishes=dishes)

        with (
            patch("sys.argv", ["menu_vision", "--image", str(img), "--output", str(out_dir)]),
            patch("menu_vision.__main__.run_pipeline", return_value=result),
        ):
            main()

        result_path = out_dir / "result.json"
        assert result_path.exists()
        data = json.loads(result_path.read_text(encoding="utf-8"))
        assert data["job_id"] == "test-job-123"
        assert data["status"] == "completed"
        assert len(data["dishes"]) == 2
        assert data["dishes"][0]["original_name"] == "Pasta"

    def test_creates_output_dir(self, tmp_path):
        img = tmp_path / "menu.jpg"
        img.write_bytes(b"fake")
        out_dir = tmp_path / "nested" / "deep" / "out"

        result = _make_result()

        with (
            patch("sys.argv", ["menu_vision", "--image", str(img), "--output", str(out_dir)]),
            patch("menu_vision.__main__.run_pipeline", return_value=result),
        ):
            main()

        assert out_dir.exists()
        assert (out_dir / "result.json").exists()

    def test_default_output_dir(self, tmp_path, monkeypatch):
        img = tmp_path / "menu.jpg"
        img.write_bytes(b"fake")
        monkeypatch.chdir(tmp_path)

        result = _make_result()

        with (
            patch("sys.argv", ["menu_vision", "--image", str(img)]),
            patch("menu_vision.__main__.run_pipeline", return_value=result),
        ):
            main()

        assert (tmp_path / "output" / "result.json").exists()


class TestCLISummary:
    def test_prints_summary(self, tmp_path, capsys):
        img = tmp_path / "menu.jpg"
        img.write_bytes(b"fake")
        out_dir = tmp_path / "out"

        dishes = [
            DishRecord(original_name="Ratatouille", translated_name="Ratatouille"),
            DishRecord(original_name="Crème Brûlée"),
        ]
        result = _make_result(dishes=dishes)

        with (
            patch("sys.argv", ["menu_vision", "--image", str(img), "--output", str(out_dir)]),
            patch("menu_vision.__main__.run_pipeline", return_value=result),
        ):
            main()

        captured = capsys.readouterr().out
        assert "test-job-123" in captured
        assert "completed" in captured
        assert "2" in captured
        assert "Ratatouille" in captured
        assert "Crème Brûlée" in captured

    def test_prints_error_message(self, tmp_path, capsys):
        img = tmp_path / "menu.jpg"
        img.write_bytes(b"fake")
        out_dir = tmp_path / "out"

        result = _make_result(status=JobStatus.FAILED, error_message="OCR failed")

        with (
            patch("sys.argv", ["menu_vision", "--image", str(img), "--output", str(out_dir)]),
            patch("menu_vision.__main__.run_pipeline", return_value=result),
        ):
            main()

        captured = capsys.readouterr().out
        assert "OCR failed" in captured

    def test_prints_translated_name(self, tmp_path, capsys):
        img = tmp_path / "menu.jpg"
        img.write_bytes(b"fake")
        out_dir = tmp_path / "out"

        dishes = [DishRecord(original_name="Boeuf", translated_name="Beef")]
        result = _make_result(dishes=dishes)

        with (
            patch("sys.argv", ["menu_vision", "--image", str(img), "--output", str(out_dir)]),
            patch("menu_vision.__main__.run_pipeline", return_value=result),
        ):
            main()

        captured = capsys.readouterr().out
        assert "Boeuf" in captured
        assert "Beef" in captured
