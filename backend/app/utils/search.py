"""LIKE patterns built from user input.

A search box value goes into ILIKE as a literal: '%' and '_' typed by a user
must match those characters, not "anything". Unescaped, searching for "%"
returned every row.
"""

LIKE_ESCAPE = "\\"


def contains(term: str) -> str:
    """'%term%' with LIKE wildcards in `term` escaped. Pair with
    `.ilike(contains(term), escape=LIKE_ESCAPE)`."""
    escaped = (
        term.replace(LIKE_ESCAPE, LIKE_ESCAPE * 2)
        .replace("%", LIKE_ESCAPE + "%")
        .replace("_", LIKE_ESCAPE + "_")
    )
    return f"%{escaped}%"
