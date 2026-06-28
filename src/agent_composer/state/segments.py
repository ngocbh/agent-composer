"""Typed runtime value system.

Every value flowing through a flow run is wrapped in a `Segment`: a frozen,
self-describing container carrying its `SegmentType`. The tag is what makes the
variable pool serialize losslessly — on a JSON round-trip the discriminated
`AnySegment` union decodes each value back into the right subclass, so an int
stays an int and a float stays a float regardless of JSON's number ambiguity.
That losslessness is the primitive durable checkpoint/resume depends on.

Trimmed from graphon's `variables/` to the load-bearing core: scalars, lists,
object — plus a reserved `FILE` placeholder that is never auto-inferred and not
yet exposed to flow authors (so adding real file handling later is additive,
not a schema migration).

This module has no package-internal dependencies on purpose; it is the leaf.
"""

from dataclasses import dataclass
from datetime import date as _date
from datetime import datetime as _datetime
from enum import Enum
from typing import Annotated, Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator


class SegmentError(ValueError):
    """A value cannot be wrapped in a Segment, or violates a declared type."""


# --------------------------------------------------------------------------- #
# Type vocabulary
# --------------------------------------------------------------------------- #


class SegmentType(str, Enum):
    """Closed type vocabulary for runtime values.

    `.value` IS the one Python-surface vocabulary: it is simultaneously the serialized
    discriminator tag, the author-written `type:` token, and the displayed name (so there
    is no second "engine name" to translate — `str`, never `string`).
    """

    NONE = "None"
    STRING = "str"
    INTEGER = "int"
    NUMBER = "float"
    DATE = "date"  # ISO-8601 calendar date, stored as str; never auto-inferred
    DATETIME = "datetime"  # ISO-8601 datetime, stored as str; never auto-inferred
    BOOLEAN = "bool"
    OBJECT = "object"
    FILE = "file"  # reserved: never auto-inferred, not authorable yet

    LIST_ANY = "list[Any]"
    LIST_STRING = "list[str]"
    LIST_INTEGER = "list[int]"
    LIST_NUMBER = "list[float]"
    LIST_BOOLEAN = "list[bool]"
    LIST_OBJECT = "list[object]"

    def is_list(self) -> bool:
        return self in _LIST_ELEMENT_TYPE

    @property
    def element_type(self) -> Optional["SegmentType"]:
        """Scalar element type for a list type (`None` for `LIST_ANY`/scalars)."""
        return _LIST_ELEMENT_TYPE.get(self)


# --------------------------------------------------------------------------- #
# Reserved FILE placeholder
# --------------------------------------------------------------------------- #


class FileRef(BaseModel):
    """A minimal, opaque file reference — reserved placeholder.

    Carries only what is needed to round-trip through a checkpoint. Storage,
    transfer, size and markdown rendering are deliberately absent until file
    handling is actually built.
    """

    model_config = ConfigDict(frozen=True)

    uri: str
    mime: Optional[str] = None
    name: Optional[str] = None


# --------------------------------------------------------------------------- #
# Segment subclasses (one per type, each pinning a Literal discriminator)
# --------------------------------------------------------------------------- #


class Segment(BaseModel):
    """Abstract base. Use a concrete subclass; construct via `build_segment`."""

    model_config = ConfigDict(frozen=True)

    value_type: SegmentType
    value: Any

    def to_object(self) -> Any:
        """The plain Python value (what expressions and node code see)."""
        return self.value

    @property
    def text(self) -> str:
        return "" if self.value is None else str(self.value)


class NoneSegment(Segment):
    value_type: Literal[SegmentType.NONE] = SegmentType.NONE
    value: None = None

    @property
    def text(self) -> str:
        return ""


class StringSegment(Segment):
    value_type: Literal[SegmentType.STRING] = SegmentType.STRING
    value: str


class IntegerSegment(Segment):
    value_type: Literal[SegmentType.INTEGER] = SegmentType.INTEGER
    value: int


class NumberSegment(Segment):
    value_type: Literal[SegmentType.NUMBER] = SegmentType.NUMBER
    value: float


class DateSegment(Segment):
    value_type: Literal[SegmentType.DATE] = SegmentType.DATE
    value: str  # ISO-8601 "YYYY-MM-DD"

    @field_validator("value")
    @classmethod
    def _iso(cls, v: str) -> str:
        _date.fromisoformat(v)  # raises ValueError if not a valid ISO date
        return v


class DateTimeSegment(Segment):
    value_type: Literal[SegmentType.DATETIME] = SegmentType.DATETIME
    value: str  # ISO-8601 "YYYY-MM-DDTHH:MM:SS[+HH:MM]"

    @field_validator("value")
    @classmethod
    def _iso(cls, v: str) -> str:
        # A bare date ("2026-06-12") parses as midnight; require a time component so
        # datetime stays distinct from date.
        if "T" not in v and " " not in v:
            raise ValueError("datetime must include a time component")
        _datetime.fromisoformat(v)  # raises ValueError if not a valid ISO datetime
        return v


class BooleanSegment(Segment):
    value_type: Literal[SegmentType.BOOLEAN] = SegmentType.BOOLEAN
    value: bool


class ObjectSegment(Segment):
    value_type: Literal[SegmentType.OBJECT] = SegmentType.OBJECT
    value: dict[str, Any]


class FileSegment(Segment):
    value_type: Literal[SegmentType.FILE] = SegmentType.FILE
    value: FileRef


class ListAnySegment(Segment):
    value_type: Literal[SegmentType.LIST_ANY] = SegmentType.LIST_ANY
    value: list[Any]


class ListStringSegment(Segment):
    value_type: Literal[SegmentType.LIST_STRING] = SegmentType.LIST_STRING
    value: list[str]


class ListIntegerSegment(Segment):
    value_type: Literal[SegmentType.LIST_INTEGER] = SegmentType.LIST_INTEGER
    value: list[int]


class ListNumberSegment(Segment):
    value_type: Literal[SegmentType.LIST_NUMBER] = SegmentType.LIST_NUMBER
    value: list[float]


class ListBooleanSegment(Segment):
    value_type: Literal[SegmentType.LIST_BOOLEAN] = SegmentType.LIST_BOOLEAN
    value: list[bool]


class ListObjectSegment(Segment):
    value_type: Literal[SegmentType.LIST_OBJECT] = SegmentType.LIST_OBJECT
    value: list[dict[str, Any]]


# Discriminated union — `value_type` selects the subclass on validate, which is
# what gives lossless decode of an arbitrary persisted segment.
AnySegment = Annotated[
    Union[
        NoneSegment,
        StringSegment,
        IntegerSegment,
        NumberSegment,
        DateSegment,
        DateTimeSegment,
        BooleanSegment,
        ObjectSegment,
        FileSegment,
        ListAnySegment,
        ListStringSegment,
        ListIntegerSegment,
        ListNumberSegment,
        ListBooleanSegment,
        ListObjectSegment,
    ],
    Field(discriminator="value_type"),
]

# Module-level adapter so callers can round-trip a bare segment losslessly.
ANY_SEGMENT_ADAPTER: TypeAdapter = TypeAdapter(AnySegment)


# --------------------------------------------------------------------------- #
# Lookup tables
# --------------------------------------------------------------------------- #

_LIST_ELEMENT_TYPE: dict[SegmentType, Optional[SegmentType]] = {
    SegmentType.LIST_ANY: None,
    SegmentType.LIST_STRING: SegmentType.STRING,
    SegmentType.LIST_INTEGER: SegmentType.INTEGER,
    SegmentType.LIST_NUMBER: SegmentType.NUMBER,
    SegmentType.LIST_BOOLEAN: SegmentType.BOOLEAN,
    SegmentType.LIST_OBJECT: SegmentType.OBJECT,
}

_SCALAR_SEGMENT_CLASS: dict[SegmentType, type[Segment]] = {
    SegmentType.NONE: NoneSegment,
    SegmentType.STRING: StringSegment,
    SegmentType.INTEGER: IntegerSegment,
    SegmentType.NUMBER: NumberSegment,
    SegmentType.DATE: DateSegment,
    SegmentType.DATETIME: DateTimeSegment,
    SegmentType.BOOLEAN: BooleanSegment,
    SegmentType.OBJECT: ObjectSegment,
    SegmentType.FILE: FileSegment,
}

_LIST_SEGMENT_CLASS: dict[SegmentType, type[Segment]] = {
    SegmentType.LIST_ANY: ListAnySegment,
    SegmentType.LIST_STRING: ListStringSegment,
    SegmentType.LIST_INTEGER: ListIntegerSegment,
    SegmentType.LIST_NUMBER: ListNumberSegment,
    SegmentType.LIST_BOOLEAN: ListBooleanSegment,
    SegmentType.LIST_OBJECT: ListObjectSegment,
}

# --------------------------------------------------------------------------- #
# Structural shape (records / variants / typed lists)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Shape:
    """Resolved runtime shape of a declared Type — drives the write-boundary check.

    `seg_type` is the storage tag (what the value persists as). The optional fields
    refine validation beyond the bare tag:
      - record:  seg_type=OBJECT,   fields={name: Shape}, required={names}
      - variant: seg_type=STRING,   tags={labels}
      - list:    seg_type=LIST_*,   element=<element Shape>
    A plain scalar / flat list uses only `seg_type` (see `Shape.scalar`).
    """

    seg_type: SegmentType
    fields: Optional[dict[str, "Shape"]] = None
    required: Optional[frozenset[str]] = None
    tags: Optional[frozenset[str]] = None
    element: Optional["Shape"] = None
    nullable: bool = False  # an Optional[X] slot — accepts None (present-None or absent)

    @classmethod
    def scalar(cls, seg: SegmentType) -> "Shape":
        return cls(seg_type=seg)


# --------------------------------------------------------------------------- #
# Scalar type checks / coercion
# --------------------------------------------------------------------------- #


def _infer_scalar_type(value: Any) -> Optional[SegmentType]:
    # bool before int — bool is a subclass of int in Python.
    if value is None:
        return SegmentType.NONE
    if isinstance(value, bool):
        return SegmentType.BOOLEAN
    if isinstance(value, int):
        return SegmentType.INTEGER
    if isinstance(value, float):
        return SegmentType.NUMBER
    if isinstance(value, str):
        return SegmentType.STRING
    if isinstance(value, FileRef):
        return SegmentType.FILE
    if isinstance(value, dict):
        return SegmentType.OBJECT
    return None


def _scalar_matches(declared: SegmentType, value: Any) -> bool:
    if declared == SegmentType.NONE:
        return value is None
    if declared == SegmentType.STRING:
        return isinstance(value, str)
    if declared == SegmentType.BOOLEAN:
        return isinstance(value, bool)
    if declared == SegmentType.INTEGER:
        return isinstance(value, int) and not isinstance(value, bool)
    if declared == SegmentType.NUMBER:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if declared == SegmentType.DATE:
        if not isinstance(value, str):
            return False
        try:
            _date.fromisoformat(value)
            return True
        except ValueError:
            return False
    if declared == SegmentType.DATETIME:
        if not isinstance(value, str):
            return False
        # a bare date is not a datetime — require an explicit time component
        if "T" not in value and " " not in value:
            return False
        try:
            _datetime.fromisoformat(value)
            return True
        except ValueError:
            return False
    if declared == SegmentType.OBJECT:
        return isinstance(value, dict)
    if declared == SegmentType.FILE:
        return isinstance(value, FileRef)
    return False


def _coerce_scalar(declared: SegmentType, value: Any) -> Any:
    # Only widening: an int may fill a NUMBER slot as a float.
    if declared == SegmentType.NUMBER and isinstance(value, int) and not isinstance(value, bool):
        return float(value)
    return value


# --------------------------------------------------------------------------- #
# Constructors
# --------------------------------------------------------------------------- #


def build_segment(value: Any) -> Segment:
    """Wrap a raw Python value in the natural Segment, inferring its type.

    `FILE` is never inferred from a dict/str — only an explicit `FileRef`
    produces a `FileSegment`. An empty list infers as `LIST_ANY`.
    """
    if isinstance(value, Segment):
        return value  # idempotent

    scalar = _infer_scalar_type(value)
    if scalar is not None:
        return _SCALAR_SEGMENT_CLASS[scalar](value=value)

    if isinstance(value, (list, tuple)):
        return _infer_list(list(value))

    raise SegmentError(f"cannot wrap value of type {type(value).__name__!r}")


def _infer_list(items: list[Any]) -> Segment:
    if not items:
        return ListAnySegment(value=[])
    element_types = {_infer_scalar_type(x) for x in items}
    if None in element_types:
        return ListAnySegment(value=items)
    if element_types == {SegmentType.STRING}:
        return ListStringSegment(value=items)
    if element_types == {SegmentType.BOOLEAN}:
        return ListBooleanSegment(value=items)
    if element_types == {SegmentType.INTEGER}:
        return ListIntegerSegment(value=items)
    if element_types <= {SegmentType.INTEGER, SegmentType.NUMBER}:
        return ListNumberSegment(value=[float(x) for x in items])
    if element_types == {SegmentType.OBJECT}:
        return ListObjectSegment(value=items)
    return ListAnySegment(value=items)


def build_segment_with_type(declared: "SegmentType | Shape", value: Any) -> Segment:
    """Wrap `value` as a Segment matching `declared`, raising on a type mismatch.

    Accepts either a bare `SegmentType` (scalar / flat list — preserved behavior)
    or a structural `Shape` (records, variants, typed/element lists). This is the
    write-boundary check the variable pool uses against each declared output type,
    so a node returning the wrong type fails loudly at the write rather than
    silently downstream.
    """
    shape = Shape.scalar(declared) if isinstance(declared, SegmentType) else declared
    if isinstance(value, Segment):
        value = value.to_object()
    return _build_for_shape(shape, value)


def _build_for_shape(shape: Shape, value: Any) -> Segment:
    # nullable (Optional[X]) — a None value is accepted as NoneSegment
    if value is None and shape.nullable:
        return NoneSegment()

    # variant — a tag-constrained string
    if shape.tags is not None:
        if not isinstance(value, str) or value not in shape.tags:
            raise SegmentError(f"{value!r} is not a member of variant {sorted(shape.tags)}")
        return StringSegment(value=value)

    # record — an object with declared field shapes (closed: all required, no unknowns)
    if shape.fields is not None:
        if not isinstance(value, dict):
            raise SegmentError(f"{value!r} is not an object for a record type")
        required = shape.required or frozenset()
        missing = required - value.keys()
        if missing:
            raise SegmentError(f"record missing required fields: {sorted(missing)}")
        unknown = value.keys() - shape.fields.keys()
        if unknown:
            raise SegmentError(f"record has unknown fields: {sorted(unknown)}")
        for fname, fval in value.items():
            _build_for_shape(shape.fields[fname], fval)  # validates each field, raises on mismatch
        return ObjectSegment(value=value)

    # list with a known element shape (incl. List[record])
    if shape.seg_type.is_list() and shape.element is not None:
        if not isinstance(value, (list, tuple)):
            raise SegmentError(
                f"{value!r} is not a list for declared {shape.seg_type.value}"
            )
        items = [_build_for_shape(shape.element, item).to_object() for item in value]
        return _LIST_SEGMENT_CLASS[shape.seg_type](value=items)

    # plain scalar / flat list — the original behavior
    return _build_scalar_or_list(shape.seg_type, value)


def _build_scalar_or_list(declared: SegmentType, value: Any) -> Segment:
    if declared.is_list():
        if not isinstance(value, (list, tuple)):
            raise SegmentError(f"{value!r} is not a list for declared {declared.value}")
        items = list(value)
        element = declared.element_type
        if element is not None:
            for item in items:
                if not _scalar_matches(element, item):
                    raise SegmentError(
                        f"list element {item!r} is not {element.value} "
                        f"(declared {declared.value})"
                    )
            items = [_coerce_scalar(element, item) for item in items]
        return _LIST_SEGMENT_CLASS[declared](value=items)

    if not _scalar_matches(declared, value):
        raise SegmentError(f"{value!r} does not match declared type {declared.value}")
    return _SCALAR_SEGMENT_CLASS[declared](value=_coerce_scalar(declared, value))
