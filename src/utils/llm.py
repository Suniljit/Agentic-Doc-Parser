import os
import sys

from dotenv import load_dotenv
from loguru import logger
from openai import OpenAI

load_dotenv()

logger.remove()
logger.add(sys.stderr, level=os.getenv("LOG_LEVEL", "INFO"))

client = OpenAI()

logger.info("OpenAI client initialized")


def get_client() -> OpenAI:
    return client
