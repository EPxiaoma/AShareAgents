"""Environment loading shared by all FastAPI startup paths."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOTENV_PATH = PROJECT_ROOT / ".env"


def load_api_environment() -> bool:
    """Load the project dotenv file without overriding process variables."""
    return load_dotenv(DOTENV_PATH, override=False)
