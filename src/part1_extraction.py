"""Extract five structured fields from the FY2024 PDF using a single GPT-4o call."""

from __future__ import annotations

from pathlib import Path

import yaml
from loguru import logger
from pydantic import BaseModel

from utils.llm import get_client
from utils.parser import parse_pages

PDF_PATH = Path("data/fy2024_analysis_of_revenue_and_expenditure.pdf")
CACHE_DIR = Path("data/cache")
MAX_TOKENS = 512

_PROMPTS = yaml.safe_load((Path(__file__).parent / "prompts.yaml").read_text())
SYSTEM_PROMPT = _PROMPTS["part1"]["extraction"]


class ExtractionResult(BaseModel):
    corporate_income_tax_2024: float
    corp_tax_yoy_pct_2024: float
    total_top_ups_2024: float
    operating_revenue_taxes: list[str]
    latest_actual_fiscal_position_bn: float


def extract() -> ExtractionResult:
    client = get_client()
    context = parse_pages(PDF_PATH, [5, 6, 8, 20], CACHE_DIR)

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": context},
        ],
        response_format={"type": "json_object"},
        max_completion_tokens=MAX_TOKENS,
        temperature=0,
    )

    result = ExtractionResult.model_validate_json(response.choices[0].message.content)

    logger.info("corporate_income_tax_2024: {}", result.corporate_income_tax_2024)
    logger.info("corp_tax_yoy_pct_2024: {}", result.corp_tax_yoy_pct_2024)
    logger.info("total_top_ups_2024: {}", result.total_top_ups_2024)
    logger.info("operating_revenue_taxes: {}", result.operating_revenue_taxes)
    logger.info("latest_actual_fiscal_position_bn: {}", result.latest_actual_fiscal_position_bn)

    return result


if __name__ == "__main__":
    result = extract()
    print(result.model_dump_json(indent=2))
