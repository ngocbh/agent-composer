"""Unit tests for the typed segment value system.

Feature -> contract:
- build_segment(value)            : raw Python value -> natural Segment
- build_segment_with_type(t, v)   : value -> Segment of declared type, or raise
- AnySegment round-trip           : JSON dumps/loads preserves the exact type
"""

import pytest

from agent_composer.state.segments import (
    ANY_SEGMENT_ADAPTER,
    BooleanSegment,
    FileRef,
    FileSegment,
    IntegerSegment,
    ListAnySegment,
    ListNumberSegment,
    ListStringSegment,
    NumberSegment,
    ObjectSegment,
    SegmentError,
    SegmentType,
    StringSegment,
    build_segment,
    build_segment_with_type,
)


# --- inference -------------------------------------------------------------- #


def test_build_segment_infers_scalars():
    assert isinstance(build_segment("hi"), StringSegment)
    assert isinstance(build_segment(3), IntegerSegment)
    assert isinstance(build_segment(3.5), NumberSegment)
    assert isinstance(build_segment({"a": 1}), ObjectSegment)
    assert build_segment(None).value_type == SegmentType.NONE


def test_bool_is_not_int():
    # bool subclasses int in Python; the value system must keep them distinct.
    assert isinstance(build_segment(True), BooleanSegment)
    assert build_segment(True).value_type == SegmentType.BOOLEAN
    assert build_segment(1).value_type == SegmentType.INTEGER


def test_list_inference():
    assert isinstance(build_segment(["a", "b"]), ListStringSegment)
    assert isinstance(build_segment([1, 2.0]), ListNumberSegment)  # mixed int/float -> number
    assert isinstance(build_segment([]), ListAnySegment)
    assert isinstance(build_segment([1, "a"]), ListAnySegment)  # heterogeneous -> any


def test_file_is_never_auto_inferred():
    # A dict that looks file-ish stays an object; only an explicit FileRef is a file.
    assert isinstance(build_segment({"uri": "s3://x"}), ObjectSegment)
    assert isinstance(build_segment(FileRef(uri="s3://x")), FileSegment)


def test_build_segment_idempotent():
    seg = build_segment(5)
    assert build_segment(seg) is seg


def test_unwrappable_value_raises():
    with pytest.raises(SegmentError):
        build_segment(object())


# --- declared-type write boundary ------------------------------------------ #


def test_with_type_widens_int_to_number():
    seg = build_segment_with_type(SegmentType.NUMBER, 7)
    assert isinstance(seg, NumberSegment)
    assert seg.value == 7.0 and isinstance(seg.value, float)


def test_with_type_rejects_mismatch():
    with pytest.raises(SegmentError):
        build_segment_with_type(SegmentType.INTEGER, "not-an-int")
    with pytest.raises(SegmentError):
        build_segment_with_type(SegmentType.INTEGER, True)  # bool is not int here


def test_with_type_typed_list_validates_elements():
    seg = build_segment_with_type(SegmentType.LIST_STRING, ["ACME", "BETA"])
    assert isinstance(seg, ListStringSegment)
    with pytest.raises(SegmentError):
        build_segment_with_type(SegmentType.LIST_STRING, ["ACME", 3])


# --- lossless serialization (the checkpoint primitive) ---------------------- #


@pytest.mark.parametrize(
    "value, expected_type, expected_py",
    [
        (3, SegmentType.INTEGER, int),
        (3.0, SegmentType.NUMBER, float),
        (True, SegmentType.BOOLEAN, bool),
        ("x", SegmentType.STRING, str),
        ({"k": [1, 2]}, SegmentType.OBJECT, dict),
        (["a", "b"], SegmentType.LIST_STRING, list),
    ],
)
def test_json_round_trip_preserves_type(value, expected_type, expected_py):
    seg = build_segment(value)
    blob = ANY_SEGMENT_ADAPTER.dump_json(seg)
    back = ANY_SEGMENT_ADAPTER.validate_json(blob)
    assert back.value_type == expected_type
    # int-vs-float-vs-bool survive the JSON number ambiguity via the type tag.
    assert type(back.value) is expected_py
    assert back.value == value


def test_file_segment_round_trip():
    seg = build_segment(FileRef(uri="s3://b/k", mime="text/csv", name="d.csv"))
    back = ANY_SEGMENT_ADAPTER.validate_json(ANY_SEGMENT_ADAPTER.dump_json(seg))
    assert isinstance(back, FileSegment)
    assert back.value.uri == "s3://b/k" and back.value.name == "d.csv"


# --- date scalar ------------------------------------------------------------ #


def test_date_segment_build_and_roundtrip():
    from agent_composer.state.segments import DateSegment

    seg = build_segment_with_type(SegmentType.DATE, "2026-06-08")
    assert isinstance(seg, DateSegment)
    assert seg.value == "2026-06-08"
    # lossless JSON round-trip via the discriminated union
    back = ANY_SEGMENT_ADAPTER.validate_python(seg.model_dump())
    assert isinstance(back, DateSegment) and back.value == "2026-06-08"


def test_date_segment_rejects_nondate():
    with pytest.raises(SegmentError):
        build_segment_with_type(SegmentType.DATE, "not-a-date")
    with pytest.raises(SegmentError):
        build_segment_with_type(SegmentType.DATE, 20260608)


def test_plain_string_not_inferred_as_date():
    assert build_segment("2026-06-08").value_type == SegmentType.STRING


# --- datetime scalar -------------------------------------------------------- #


def test_datetime_segment_build_and_roundtrip():
    from agent_composer.state.segments import DateTimeSegment

    seg = build_segment_with_type(SegmentType.DATETIME, "2026-06-12T14:30:00+00:00")
    assert isinstance(seg, DateTimeSegment)
    assert seg.value == "2026-06-12T14:30:00+00:00"
    # lossless JSON round-trip via the discriminated union
    back = ANY_SEGMENT_ADAPTER.validate_python(seg.model_dump())
    assert isinstance(back, DateTimeSegment) and back.value == "2026-06-12T14:30:00+00:00"


def test_datetime_segment_rejects_nondatetime():
    with pytest.raises(SegmentError):
        build_segment_with_type(SegmentType.DATETIME, "not-a-datetime")
    with pytest.raises(SegmentError):
        build_segment_with_type(SegmentType.DATETIME, 20260612)


def test_datetime_distinct_from_date():
    # a bare DATE string must NOT type-check as a datetime (date and datetime are distinct
    # scalars; datetime.fromisoformat would otherwise accept a bare date as midnight).
    with pytest.raises(SegmentError):
        build_segment_with_type(SegmentType.DATETIME, "2026-06-12")
    # and a datetime string is not a date
    with pytest.raises(SegmentError):
        build_segment_with_type(SegmentType.DATE, "2026-06-12T14:30:00+00:00")


def test_plain_string_not_inferred_as_datetime():
    assert build_segment("2026-06-12T14:30:00+00:00").value_type == SegmentType.STRING


# --- structural Shape (records / variants / typed lists) -------------------- #


def test_shape_back_compat_segmenttype_still_accepted():
    from agent_composer.state.segments import Shape

    assert isinstance(build_segment_with_type(Shape.scalar(SegmentType.STRING), "x"), StringSegment)
    # passing a bare SegmentType still works (back-compat)
    assert build_segment_with_type(SegmentType.NUMBER, 3).value == 3.0


def test_shape_variant_membership():
    from agent_composer.state.segments import Shape

    action = Shape(seg_type=SegmentType.STRING, tags=frozenset({"Approve", "Reject", "Defer"}))
    assert build_segment_with_type(action, "Approve").value == "Approve"
    with pytest.raises(SegmentError):
        build_segment_with_type(action, "approve")


def test_shape_record_fields():
    from agent_composer.state.segments import Shape

    rating = Shape(
        seg_type=SegmentType.OBJECT,
        fields={
            "value": Shape.scalar(SegmentType.NUMBER),
            "confidence": Shape.scalar(SegmentType.NUMBER),
        },
        required=frozenset({"value", "confidence"}),
    )
    assert isinstance(build_segment_with_type(rating, {"value": 0.8, "confidence": 0.9}), ObjectSegment)
    with pytest.raises(SegmentError):  # missing required field
        build_segment_with_type(rating, {"value": 0.8})
    with pytest.raises(SegmentError):  # unknown field
        build_segment_with_type(rating, {"value": 0.8, "confidence": 0.9, "x": 1})
    with pytest.raises(SegmentError):  # wrong field type
        build_segment_with_type(rating, {"value": "hi", "confidence": 0.9})


def test_shape_nullable_field_accepts_none_and_absent():
    from agent_composer.state.segments import Shape

    sig = Shape(
        seg_type=SegmentType.OBJECT,
        fields={
            "score": Shape.scalar(SegmentType.NUMBER),
            "note": Shape(seg_type=SegmentType.STRING, nullable=True),
        },
        required=frozenset({"score"}),  # note is Optional -> not required
    )
    # present-None on the nullable field -> ok
    assert isinstance(build_segment_with_type(sig, {"score": 0.5, "note": None}), ObjectSegment)
    # absent nullable field -> ok
    assert isinstance(build_segment_with_type(sig, {"score": 0.5}), ObjectSegment)
    # a present non-null value on the nullable field still type-checks
    assert isinstance(build_segment_with_type(sig, {"score": 0.5, "note": "hi"}), ObjectSegment)
    # a non-nullable field still rejects None
    with pytest.raises(SegmentError):
        build_segment_with_type(sig, {"score": None, "note": "x"})


def test_shape_list_of_record():
    from agent_composer.state.segments import ListObjectSegment, Shape

    rating = Shape(
        seg_type=SegmentType.OBJECT,
        fields={"value": Shape.scalar(SegmentType.NUMBER)},
        required=frozenset({"value"}),
    )
    lst = Shape(seg_type=SegmentType.LIST_OBJECT, element=rating)
    seg = build_segment_with_type(lst, [{"value": 1.0}, {"value": 2.0}])
    assert isinstance(seg, ListObjectSegment) and len(seg.value) == 2
    with pytest.raises(SegmentError):
        build_segment_with_type(lst, [{"value": "bad"}])
