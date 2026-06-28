"""Typed runtime state: the segment value system + the variable pool."""

from agent_composer.state.pool import TypedVariablePool
from agent_composer.state.segments import (
    AnySegment,
    DateSegment,
    DateTimeSegment,
    FileRef,
    Segment,
    SegmentError,
    SegmentType,
    Shape,
    build_segment,
    build_segment_with_type,
)
from agent_composer.state.types import (
    ListType,
    RecordDef,
    RefType,
    ScalarType,
    Type,
    TypeRegistry,
    VariantDef,
    parse_type,
    resolve_shape,
    shape_for,
)

__all__ = [
    "AnySegment",
    "DateSegment",
    "DateTimeSegment",
    "FileRef",
    "ListType",
    "RecordDef",
    "RefType",
    "ScalarType",
    "Segment",
    "SegmentError",
    "SegmentType",
    "Shape",
    "Type",
    "TypeRegistry",
    "TypedVariablePool",
    "VariantDef",
    "build_segment",
    "build_segment_with_type",
    "parse_type",
    "resolve_shape",
    "shape_for",
]
