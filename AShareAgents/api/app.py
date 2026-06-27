"""AShareAgents 的 FastAPI 应用工厂。"""

from __future__ import annotations

from fastapi import FastAPI

from AShareAgents.api.environment import load_api_environment

load_api_environment()

from AShareAgents.api.routes import router


def create_app() -> FastAPI:
    app = FastAPI(
        title="AShareAgents API",
        version="1.0.0",
        description="HTTP backend for the AShareAgents Streamlit frontend.",
    )
    app.include_router(router)
    return app


app = create_app()
