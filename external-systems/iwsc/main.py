"""
main.py — iWISC FastAPI service entry point.

Run with:
    uvicorn main:app --port 8765 --reload

Swagger UI: http://localhost:8765/docs
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import init_db
from seed_data import seed_if_empty
from routers.tasks import router as tasks_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize DB schema and seed data
    init_db()
    seed_if_empty()
    yield
    # Shutdown: nothing to clean up for SQLite


app = FastAPI(
    title="iWISC AOI External System",
    description=(
        "Simulates the iWISC AOI external system. "
        "Provides task management and annotation result reception APIs "
        "for CIM platform integration testing."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# Allow all origins for development / integration testing
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tasks_router, tags=["Tasks"])


@app.get("/health", tags=["Health"])
def health():
    """Quick health check — returns service status."""
    return {"status": "ok", "service": "iWISC"}
