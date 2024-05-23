"""Module with custom collections classes."""

from __future__ import annotations

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
