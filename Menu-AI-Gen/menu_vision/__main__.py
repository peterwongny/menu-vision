"""Local CLI entry point for Menu Vision pipeline.

Usage:
    python -m menu_vision --image menu.jpg --output ./results/
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from menu_vision.pipeline import run_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Menu Vision — extract and translate restaurant menu items from a photo"
    )
    parser.add_argument(
        "--image", required=True, help="Path to the menu image file"
    )
    parser.add_argument(
        "--output",
        default="./output",
        help="Output directory for results (default: ./output)",
    )
    args = parser.parse_args()

    if not os.path.isfile(args.image):
        print(f"Error: image file not found: {args.image}", file=sys.stderr)
        sys.exit(1)

    os.makedirs(args.output, exist_ok=True)

    print(f"Processing {args.image} ...")
    result = run_pipeline(args.image)

    # Save result JSON
    result_path = os.path.join(args.output, "result.json")
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(result.to_json(), f, indent=2, ensure_ascii=False)

    # Print summary
    print(f"\nJob ID:  {result.job_id}")
    print(f"Status:  {result.status.value}")
    print(f"Dishes:  {len(result.dishes)}")
    if result.dishes:
        for i, dish in enumerate(result.dishes):
            print(f"  [{i}] {dish.original_name}", end="")
            if dish.translated_name:
                print(f" — {dish.translated_name}", end="")
            print()
    if result.error_message:
        print(f"Error:   {result.error_message}")
    print(f"\nResults saved to {result_path}")


if __name__ == "__main__":
    main()
