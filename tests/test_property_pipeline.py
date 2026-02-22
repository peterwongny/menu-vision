# Feature: menu-vision, Property 7: Partial results on pipeline dish failure
"""Property-based tests for pipeline partial failure resilience."""

from unittest.mock import patch

from hypothesis import given, settings
from hypothesis import strategies as st

from menu_vision.models import DishRecord, JobStatus
from menu_vision.pipeline import PLACEHOLDER_IMAGE_URL, run_pipeline


# Strategy: generate a random list of DishRecord objects (1-20 dishes)
dish_record_strategy = st.builds(
    DishRecord,
    original_name=st.text(
        alphabet=st.characters(blacklist_categories=("Cs",)),
        min_size=1,
    ).filter(lambda s: s.strip()),
    translated_name=st.one_of(st.none(), st.text(min_size=1)),
    description=st.one_of(st.none(), st.text(min_size=1)),
    ingredients=st.lists(st.text(min_size=1), max_size=5),
    price=st.one_of(st.none(), st.text(min_size=1)),
    image_url=st.none(),
)

# Strategy: list of dishes paired with a boolean mask for image gen failures
dishes_with_failures_strategy = st.lists(
    st.tuples(dish_record_strategy, st.booleans()),
    min_size=1,
    max_size=20,
)


@settings(max_examples=100)
@given(dishes_and_mask=dishes_with_failures_strategy)
def test_partial_results_on_pipeline_dish_failure(
    dishes_and_mask: list[tuple[DishRecord, bool]],
):
    """**Validates: Requirements 7.1, 4.4**"""
    dishes = [d for d, _ in dishes_and_mask]
    failure_mask = [fail for _, fail in dishes_and_mask]

    # Build the mock return value for generate_all_dish_images:
    # (idx, bytes) for successes, (idx, None) for failures
    image_results = [
        (idx, None if fails else b"fake-png-bytes")
        for idx, fails in enumerate(failure_mask)
    ]

    with (
        patch("menu_vision.pipeline.extract_text", return_value="dummy ocr text"),
        patch("menu_vision.pipeline.structure_menu", return_value=dishes),
        patch(
            "menu_vision.pipeline.generate_all_dish_images",
            return_value=image_results,
        ),
    ):
        result = run_pipeline(image_bytes=b"fake")

    # All dishes must be present — none dropped
    assert len(result.dishes) == len(dishes)

    # Each dish must have the correct image_url based on the failure mask
    for idx, (dish, failed) in enumerate(zip(result.dishes, failure_mask)):
        if failed:
            assert dish.image_url == PLACEHOLDER_IMAGE_URL, (
                f"Dish {idx} should have placeholder URL (image gen failed), "
                f"got {dish.image_url!r}"
            )
        else:
            assert dish.image_url == f"generated://dish_{idx}.png", (
                f"Dish {idx} should have generated URL (image gen succeeded), "
                f"got {dish.image_url!r}"
            )

    # Status should be PARTIAL if any failures, COMPLETED if all succeeded
    any_failed = any(failure_mask)
    if any_failed:
        assert result.status == JobStatus.PARTIAL
    else:
        assert result.status == JobStatus.COMPLETED
