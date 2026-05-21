"""Extract and classify two dates from the FY2024 PDF using GPT-4o tool calling and FastMCP."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import yaml
from loguru import logger
from mcp.client.stdio import stdio_client

from mcp import ClientSession, StdioServerParameters
from utils.llm import get_client
from utils.logging_config import setup_file_logging
from utils.parser import parse_pages

PDF_PATH = Path("data/fy2024_analysis_of_revenue_and_expenditure.pdf")
CACHE_DIR = Path("data/cache")
MAX_TOKENS_EXTRACTION = 512
MAX_TOKENS_CLASSIFICATION = 512

_PROMPTS = yaml.safe_load((Path(__file__).parent / "prompts.yaml").read_text())

NORMALIZE_DATE_TOOL = {
    "type": "function",
    "function": {
        "name": "normalize_date",
        "description": "Normalize a date string to ISO 8601 (YYYY-MM-DD)",
        "parameters": {
            "type": "object",
            "properties": {
                "date_text": {"type": "string", "description": "Raw date string to normalize"},
                "original_text": {"type": "string", "description": "Full sentence where the date appeared"},
            },
            "required": ["date_text", "original_text"],
        },
    },
}


async def call_mcp_tool(tool_name: str, arguments: dict) -> str:
    server_params = StdioServerParameters(command="uv", args=["run", "mcp/datetime_server.py"])
    start = time.perf_counter()
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
    elapsed = time.perf_counter() - start
    logger.debug("MCP round-trip ({}): {:.3f}s", tool_name, elapsed)
    return result.content[0].text


async def extract_dates(client, context: str) -> list[dict]:
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": _PROMPTS["part2"]["extraction"]},
            {"role": "user", "content": context},
        ],
        tools=[NORMALIZE_DATE_TOOL],
        tool_choice="auto",
        max_completion_tokens=MAX_TOKENS_EXTRACTION,
        temperature=0,
    )

    msg = response.choices[0].message
    logger.debug("GPT-4o response — content: {}, tool_calls: {}", msg.content, msg.tool_calls)

    if not msg.tool_calls:
        logger.warning("GPT-4o returned no tool calls — cannot extract dates")
        return []

    pairs = []
    for tc in msg.tool_calls:
        args = json.loads(tc.function.arguments)
        logger.debug("Tool input — {}: {}", tc.function.name, args)
        normalized_date = await call_mcp_tool(tc.function.name, {"date_text": args["date_text"]})
        logger.debug("Tool output — {}: {}", tc.function.name, normalized_date)
        pairs.append({"original_text": args["original_text"], "normalized_date": normalized_date})

    logger.debug("Extracted date pairs: {}", pairs)
    return pairs


async def classify_dates(client, date_pairs: list[dict]) -> list[dict]:
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": _PROMPTS["part2"]["classification"]},
            {"role": "user", "content": json.dumps(date_pairs, indent=2)},
        ],
        response_format={"type": "json_object"},
        max_completion_tokens=MAX_TOKENS_CLASSIFICATION,
        temperature=0,
    )

    raw = json.loads(response.choices[0].message.content)
    if isinstance(raw, list):
        return raw
    return next(iter(raw.values()))


async def main() -> None:
    client = get_client()
    context = parse_pages(PDF_PATH, [1, 36], CACHE_DIR)

    logger.info("Extracting dates via GPT-4o tool calling")
    date_pairs = await extract_dates(client, context)

    if not date_pairs:
        logger.warning("No date pairs extracted; skipping classification")
        print("[]")
        return

    logger.info("Classifying {} date(s) against reference date 2024-01-01", len(date_pairs))
    logger.debug("Classifier input: {}", date_pairs)
    results = await classify_dates(client, date_pairs)

    logger.info("Classification complete: {}", results)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    setup_file_logging("part2")
    asyncio.run(main())
