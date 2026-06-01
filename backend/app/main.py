from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.pipeline import router as pipeline_router


def create_app() -> FastAPI:
    app = FastAPI(title="Stock Income Agent", version="0.1.0")
    app.include_router(health_router)
    app.include_router(pipeline_router)
    return app


app = create_app()
