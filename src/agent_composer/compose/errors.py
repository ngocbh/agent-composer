"""Loud, locatable errors for the Compose loader."""

from typing import Optional


class LoadError(ValueError):
    """A Compose flow cannot be loaded (bad shape, type, or structure).

    `.line` carries the source `.yaml` line when known (filled in by later slices
    that track positions); it is None for errors raised away from a parsed node.
    """

    def __init__(self, message: str, line: Optional[int] = None):
        super().__init__(message)
        self.line = line
