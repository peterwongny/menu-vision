# Feature: menu-vision, Property 5: DishRecord JSON round-trip
"""Property-based tests for DishRecord JSON serialization round-trip."""

from hypothesis import given, settings
from hypothesis import strategies as st

from menu_vision.models import DishRecord


dish_record_strategy = st.builds(
    DishRecord,
    original_name=st.text(min_size=1),
    translated_name=st.one_of(st.none(), st.text()),
    description=st.one_of(st.none(), st.text()),
    ingredients=st.lists(st.text()),
    price=st.one_of(st.none(), st.text()),
    image_url=st.one_of(st.none(), st.text()),
)


@settings(max_examples=100)
@given(dish=dish_record_strategy)
def test_dish_record_json_round_trip(dish: DishRecord):
    """**Validates: Requirements 3.5**"""
    serialized = dish.to_json()
    deserialized = DishRecord.from_json(serialized)
    assert deserialized == dish
