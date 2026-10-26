"""Load & expose cấu hình từ .env"""
import os
from pathlib import Path

# Load .env ở thư mục gốc backend/
try:
    from dotenv import load_dotenv

    _ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(dotenv_path=_ENV_FILE)
except ImportError:  # pragma: no cover
    pass


class Settings:
    youtube_api_key: str = os.getenv("YOUTUBE_API_KEY", "").strip()
    host: str = os.getenv("APP_HOST", "0.0.0.0")
    port: int = int(os.getenv("APP_PORT", "8000"))
    cors_origins: list[str] = [
        o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()
    ] or ["*"]


settings = Settings()