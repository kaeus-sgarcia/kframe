"""Module with custom collections classes."""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum
from functools import total_ordering


@total_ordering
class OrderedEnum(Enum):
    """OrderedEnum class that allows ordering according to attributes position and allows comparing enum values with strings."""

    def __lt__(self: OrderedEnum, other: OrderedEnum | str) -> bool:
        """Compare two OrderedEnum values.

        Args:
            other (OrderedEnum | str): Value to compare.

        Returns:
            bool: True if self is less than other, False otherwise.
        """
        if isinstance(other, str):
            other = self.__class__(other)
        if not isinstance(other, self.__class__):
            raise TypeError(f"Cannot compare {self.__class__} with {type(other)}")
        if self == other:
            return False
        for elem in self.__class__:
            if self == elem:
                return True
            return False
        return False


class DictObject(dict):
    """DictObject class that allows accessing dictionary values as attributes."""

    def __init__(self, *args, **kwargs):
        """Initialize DictObject.

        Args:
            *args: Dictionaries to merge.
            **kwargs: Key-value pairs to merge.

        Raises:
            TypeError: If any of the arguments is not a mapping.
        """
        _dict = {}
        for arg in args:
            if not isinstance(arg, Mapping):
                raise TypeError(f"Invalid mapping type {type(arg)}")
            _dict = _dict | {k: DictObject(v) if isinstance(v, Mapping) else v for k, v in arg.items()}

        _dict = _dict | {k: DictObject(v) if isinstance(v, Mapping) else v for k, v in kwargs.items()}
        super().__init__(_dict)

    def __getattr__(self, name, default=None):
        """Get attribute by name.

        Args:
            name (str): Attribute name.
            default: Default value.

        Returns:
            Any: Attribute value.
        """
        if name not in self:
            raise AttributeError(f"Invalid attribute {name}")
        return self[name]
