from __future__ import annotations

from dateutil import parser as dateutil_parser
from fastmcp import FastMCP
from loguru import logger

mcp = FastMCP("datetime-server")


@mcp.tool()
def normalize_date(date_text: str) -> str:
    """Parse a natural-language date string and return it in ISO 8601 format (YYYY-MM-DD).
    Returns an error string if the date cannot be parsed.
    """
    try:
        date = dateutil_parser.parse(date_text)
        result = date.date().isoformat()
        logger.debug("normalize_date: '{}' → '{}'", date_text, result)
        return result
    except Exception as exc:
        logger.debug("normalize_date: could not parse '{}': {}", date_text, exc)
        return f"ERROR: could not parse '{date_text}'"


if __name__ == "__main__":
    mcp.run(transport="stdio")
