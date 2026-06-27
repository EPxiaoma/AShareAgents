"""FastAPI 后端的 CLI 入口。"""

from __future__ import annotations

import os

import uvicorn


def main() -> None:
    uvicorn.run(
        "AShareAgents.api.app:app",
        host=os.getenv("ASHAREAGENTS_API_HOST", "127.0.0.1"),
        port=int(os.getenv("ASHAREAGENTS_API_PORT", "8000")),
        reload=False,
    )


if __name__ == "__main__":
    main()
