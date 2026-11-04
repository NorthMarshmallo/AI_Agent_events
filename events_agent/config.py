import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

ROOT = Path(__file__).resolve().parent.parent
DATA, TRACES, LOGS = ROOT / "data", ROOT / "traces", ROOT / "logs"
if load_dotenv:
    load_dotenv(ROOT / ".env")

BASE_URL = "https://openrouter.ai/api/v1"
CHEAP, MID, STRONG = "openai/gpt-4o-mini", "anthropic/claude-haiku-4.5", "anthropic/claude-sonnet-4.6"
EMBED_MODEL, DIM = "openai/text-embedding-3-small", 512
MILVUS_URI = os.getenv("MILVUS_URI", "http://localhost:19530")


def api_key():
    key = os.getenv("OPENROUTER_API_KEY")
    if not key or key == "your-key":
        raise SystemExit("нет ключа: впишите OPENROUTER_API_KEY в .env в корне проекта")
    return key
