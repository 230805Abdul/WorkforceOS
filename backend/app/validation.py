"""Shared input rules (Phase 4).

Validation, not "sanitising": we don't strip quotes or <, > from names (O'Brien and <Acme> are legitimate data;
safety comes from parameterised SQL and React's escaping). We DO refuse control characters: they are never legitimate
in names or e-mails, PostgreSQL rejects NUL bytes (that used to cause a 500 error), and they can forge log lines.
"""
import re
from typing import Annotated

from fastapi import Query
from pydantic import AfterValidator, ConfigDict, StringConstraints

_SINGLE_LINE_FORBIDDEN = re.compile(r"[\x00-\x1f\x7f]")       # every control character
_MULTI_LINE_FORBIDDEN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")  # ...except tab, newline, carriage return


def _single_line(value: str) -> str:
    if _SINGLE_LINE_FORBIDDEN.search(value):
        raise ValueError("Contains characters that aren't allowed")
    return value


def _multi_line(value: str) -> str:
    if _MULTI_LINE_FORBIDDEN.search(value):
        raise ValueError("Contains characters that aren't allowed")
    return value


def text(min_length: int, max_length: int, *, multiline: bool = False):
    """A trimmed string of bounded length without control characters."""
    return Annotated[str, StringConstraints(strip_whitespace=True, min_length=min_length, max_length=max_length),
                     AfterValidator(_multi_line if multiline else _single_line)]


# Secrets (passwords) are never trimmed: spaces are allowed. Only NUL is refused.
def _no_nul(value: str) -> str:
    if "\x00" in value:
        raise ValueError("Contains characters that aren't allowed")
    return value


SecretText = Annotated[str, StringConstraints(min_length=1, max_length=1024), AfterValidator(_no_nul)]

# Unknown fields are an error, not silently ignored: protects against mass assignment and catches client bugs.
STRICT = ConfigDict(extra="forbid")

# Query parameters
SearchQuery = Annotated[str | None, Query(max_length=100, pattern=r"^[^\x00-\x1f\x7f]*$")]
