# src.common.helpers
from typing import Callable

from src.core.exceptions import BadRequestError
from src.core.types import ALLOWED_IMAGE_TYPES


def compose(*functions: Callable) -> Callable:
    """
    Composes multiple functions into a single callable, applying them
    from right to left. The rightmost function can accept multiple arguments;
    the rest must be single-argument functions.

    Example:
        def add(x, y): return x + y
        def square(x): return x * x

        f = compose(square, add)
        f(2, 3)  # Output: 25, since add(2, 3) = 5 → square(5) = 25

    Args:
        *functions: A sequence of callables.

    Returns:
        A callable that applies the given functions from right to left.
    """

    def composed(*args, **kwargs):
        result = functions[-1](*args, **kwargs)
        for fn in reversed(functions[:-1]):
            result = fn(result)
        return result

    return composed


def pipe(*functions: Callable) -> Callable:
    """
    Pipes a value through a sequence of functions, applying them from left to right.
    The leftmost function can accept multiple arguments; the rest must be single-argument.

    Example:
        def add(x, y): return x + y
        def square(x): return x * x

        f = pipe(add, square)
        f(2, 3)  # Output: 25, since add(2, 3) = 5 → square(5) = 25

    Args:
        *functions: A sequence of callables.

    Returns:
        A callable that applies the given functions from left to right.
    """

    def piped(*args, **kwargs):
        result = functions[0](*args, **kwargs)
        for fn in functions[1:]:
            result = fn(result)
        return result

    return piped


def get_extension_for_content_type(content_type: str) -> str:
    """
    Return the supported file extension for a MIME type.

    Raises:
        BadRequestError: If the content type is unsupported.
    """
    extension = ALLOWED_IMAGE_TYPES.get(content_type)

    if not extension:
        raise BadRequestError("Unsupported image type.")

    return extension
