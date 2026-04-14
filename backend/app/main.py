"""Main FastAPI application for Dhwani Sutra."""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_config
from app.utils.logging import get_logger, setup_logging

# Setup logging on module import
setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Lifespan context manager for startup and shutdown events."""
    config = get_config()
    logger.info(
        "application_starting",
        provider=config.provider,
        test_mode=config.test_mode,
        host=config.host,
        port=config.port,
    )

    # Startup tasks
    from app.websocket.gateway import get_session_manager

    session_manager = get_session_manager()
    await session_manager.start_cleanup_task()
    logger.info("session_cleanup_task_started")

    yield

    # Shutdown tasks
    logger.info("application_shutting_down")
    await session_manager.close_all()
    logger.info("all_resources_cleaned_up")


# Create FastAPI app
app = FastAPI(
    title="Dhwani Sutra",
    description="Production-grade real-time Speech-to-Text streaming platform",
    version="0.1.0",
    lifespan=lifespan,
)

# Configure CORS
config = get_config()
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.security.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint."""
    return {
        "name": "Dhwani Sutra",
        "description": "Real-time Speech-to-Text streaming platform",
        "version": "0.1.0",
    }


@app.get("/health")
async def health() -> JSONResponse:
    """Health check endpoint."""
    config = get_config()
    return JSONResponse(
        content={
            "status": "healthy",
            "provider": config.provider,
            "test_mode": config.test_mode,
        }
    )


@app.get("/ready")
async def readiness() -> JSONResponse:
    """Readiness check endpoint."""
    # Check if all required services are available
    # - Redis connection if enabled
    # - Provider API connectivity
    return JSONResponse(content={"status": "ready"})


# Include WebSocket routes
from app.websocket.gateway import router as websocket_router

app.include_router(websocket_router)


if __name__ == "__main__":
    import uvicorn

    config = get_config()
    uvicorn.run(
        "app.main:app",
        host=config.host,
        port=config.port,
        reload=config.debug,
        log_config=None,  # Use our custom logging
    )
