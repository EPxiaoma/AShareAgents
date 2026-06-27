"""所有 FastAPI 启动路径共享的环境加载逻辑。"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOTENV_PATH = PROJECT_ROOT / ".env"


def load_api_environment() -> bool:
    """加载项目 dotenv 文件，但不覆盖已有进程变量。"""
    return load_dotenv(DOTENV_PATH, override=False)
