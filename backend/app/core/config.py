import os
from pathlib import Path

from dotenv import load_dotenv


load_dotenv(encoding="utf-8-sig")

BASE_DIR = Path(__file__).resolve().parents[2]
DATABASE_URL = f"sqlite:///{BASE_DIR / 'actionbridge.db'}"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
PARSER_PROVIDER = os.getenv("ACTIONBRIDGE_PARSER_PROVIDER", "deepseek")
FEISHU_WEBHOOK_URL = os.getenv("FEISHU_WEBHOOK_URL")
