import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import MONITOR_VERSION, SERVICE_NAME
from app import routes
from app.scheduler import setup_scheduler, shutdown_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("%s v%s starting up.", SERVICE_NAME, MONITOR_VERSION)
    setup_scheduler()
    yield
    shutdown_scheduler()
    logger.info("Shutting down.")


app = FastAPI(
    title="Monitor Service",
    description="System metrics sidecar for container stats, disk usage, and daily health reports.",
    version=MONITOR_VERSION,
    lifespan=lifespan,
)

app.include_router(routes.router)
