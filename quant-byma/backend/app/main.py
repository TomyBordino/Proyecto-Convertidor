import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.events_routes import router as events_router
from app.api.portfolio_routes import router as portfolio_router
from app.api.routes import router
from app.config import get_settings
from app.db.session import init_engine
from app.scheduler import start_scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_engine()
    scheduler = start_scheduler() if get_settings().scheduler_enabled else None
    yield
    if scheduler:
        scheduler.shutdown(wait=False)


app = FastAPI(title="Quant BYMA API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
app.include_router(events_router)
app.include_router(portfolio_router)
