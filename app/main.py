"""My Meal Plan – FastAPI application entry point."""

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import api, config, db, notifier, ui

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    stop = asyncio.Event()
    task = asyncio.create_task(notifier.run_scheduler(stop)) if config.SCHEDULER_ENABLED else None
    yield
    stop.set()
    if task:
        await task


app = FastAPI(title="My Meal Plan", version="1.0.0", lifespan=lifespan, docs_url="/api/docs", redoc_url=None)

config.ensure_dirs()
app.mount("/static", StaticFiles(directory=config.APP_DIR / "static"), name="static")
app.mount("/uploads", StaticFiles(directory=config.UPLOAD_DIR), name="uploads")
app.include_router(api.router)
app.include_router(ui.router)
