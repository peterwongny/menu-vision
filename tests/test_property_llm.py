# Feature: menu-vision, Property 3: LLM response parsing produces complete DishRecords
"""Property-based tests for LLM response parsing into DishRecords."""

import json

from hypothesis import given, settings
from hypothesis import strategies as st

from backend.llm import parse_llm_response
from backend.models import DishRecord

# Strategy for a single dish object conforming to the LLM output schema
dish_json_strategy = st.fixed_dictionaries(
    {
        "original_name": st.text(
            alphabet=st.characters(blacklist_categories=("Cs",)),
            min_size=1,
        ).filter(lambda s: s.strip()),
    },
    optional={
        "translated_name": st.one_of(st.none(), st.text(min_size=1).filter(lambda s: s.strip())),
        "description": st.one_of(st.none(), st.text(min_size=1).filter(lambda s: s.strip())),
        "cuisine": st.one_of(st.none(), st.text(min_size=1).filter(lambda s: s.strip())),
        "ingredients": st.lists(st.text(min_size=1), max_size=15),
        "price": st.one_of(st.none(), st.text(min_size=1).filter(lambda s: s.strip())),
    },
)

# Strategy for a JSON array of dish objects
dishes_json_array_strategy = st.lists(dish_json_strategy, min_size=1, max_size=10)


@settings(max_examples=100)
@given(dishes_data=dishes_json_array_strategy)
def test_llm_response_parsing_produces_complete_dish_records(
    dishes_data: list[dict],
):
    """**Validates: Requirements 3.1, 3.2**"""
    json_string = json.dumps(dishes_data)
    result = parse_llm_response(json_string)

    assert isinstance(result, list)
    assert len(result) == len(dishes_data)

    for dish in result:
        assert isinstance(dish, DishRecord)

        # original_name must be a non-empty string
        assert isinstance(dish.original_name, str)
        assert len(dish.original_name) > 0

        # translated_name is either a non-empty string or None
        assert dish.translated_name is None or (
            isinstance(dish.translated_name, str) and len(dish.translated_name) > 0
        )

        # description is either a non-empty string or None
        assert dish.description is None or (
            isinstance(dish.description, str) and len(dish.description) > 0
        )

        # cuisine is either a non-empty string or None
        assert dish.cuisine is None or (
            isinstance(dish.cuisine, str) and len(dish.cuisine) > 0
        )

        # ingredients is a list of strings (possibly empty)
        assert isinstance(dish.ingredients, list)
        for ingredient in dish.ingredients:
            assert isinstance(ingredient, str)

        # price is either a non-empty string or None
        assert dish.price is None or (
            isinstance(dish.price, str) and len(dish.price) > 0
        )

        # image_url is None (not set by parse_llm_response)
        assert dish.image_url is None


# Feature: menu-vision, Property 4: Unknown fields are None, not fabricated

# Strategy: for each optional field, either set it to None or omit it entirely from the dict.
# original_name is always a non-empty string.
# After parsing, verify that absent/null fields map to None (or [] for ingredients),
# and that no fabricated default string values appear.

_OPTIONAL_FIELD_ABSENT = st.just("__absent__")


def _build_dish_with_unknown_fields(
    original_name: str,
    translated_name_choice,
    description_choice,
    price_choice,
    ingredients_choice,
) -> dict:
    """Build a dish dict where optional fields are either null or absent."""
    dish: dict = {"original_name": original_name}
    if translated_name_choice != "__absent__":
        dish["translated_name"] = translated_name_choice  # will be None
    if description_choice != "__absent__":
        dish["description"] = description_choice  # will be None
    if price_choice != "__absent__":
        dish["price"] = price_choice  # will be None
    if ingredients_choice == "__absent__":
        pass  # omit entirely
    elif ingredients_choice is None:
        dish["ingredients"] = None
    else:
        dish["ingredients"] = []  # empty list
    return dish


# Each optional field is either null or absent from the dict.
# ingredients can also be an empty list.
unknown_dish_strategy = st.builds(
    _build_dish_with_unknown_fields,
    original_name=st.text(
        alphabet=st.characters(blacklist_categories=("Cs",)),
        min_size=1,
    ).filter(lambda s: s.strip()),
    translated_name_choice=st.one_of(st.just(None), _OPTIONAL_FIELD_ABSENT),
    description_choice=st.one_of(st.just(None), _OPTIONAL_FIELD_ABSENT),
    price_choice=st.one_of(st.just(None), _OPTIONAL_FIELD_ABSENT),
    ingredients_choice=st.one_of(st.just(None), _OPTIONAL_FIELD_ABSENT, st.just([])),
)

unknown_dishes_strategy = st.lists(unknown_dish_strategy, min_size=1, max_size=10)


@settings(max_examples=100)
@given(dishes_data=unknown_dishes_strategy)
def test_unknown_fields_are_none_not_fabricated(dishes_data: list[dict]):
    """**Validates: Requirements 3.4**"""
    json_string = json.dumps(dishes_data)
    result = parse_llm_response(json_string)

    assert len(result) == len(dishes_data)

    for dish, source in zip(result, dishes_data):
        assert isinstance(dish, DishRecord)
        assert dish.original_name == source["original_name"].strip()

        # translated_name: if null or absent in source, must be None in DishRecord
        if source.get("translated_name") is None:
            assert dish.translated_name is None, (
                f"translated_name should be None, got {dish.translated_name!r}"
            )

        # description: if null or absent in source, must be None in DishRecord
        if source.get("description") is None:
            assert dish.description is None, (
                f"description should be None, got {dish.description!r}"
            )

        # price: if null or absent in source, must be None in DishRecord
        if source.get("price") is None:
            assert dish.price is None, (
                f"price should be None, got {dish.price!r}"
            )

        # ingredients: if null, absent, or empty list in source, must be [] in DishRecord
        raw_ingredients = source.get("ingredients")
        if raw_ingredients is None or raw_ingredients == []:
            assert dish.ingredients == [], (
                f"ingredients should be [], got {dish.ingredients!r}"
            )

        # Verify no fabricated default string values appear for unknown fields
        # A fabricated value would be a non-None string when the source had null/absent
        if "translated_name" not in source or source["translated_name"] is None:
            assert dish.translated_name is None
        if "description" not in source or source["description"] is None:
            assert dish.description is None
        if "price" not in source or source["price"] is None:
            assert dish.price is None
