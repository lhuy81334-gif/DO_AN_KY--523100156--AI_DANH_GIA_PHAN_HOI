import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.api.router import api_router
from app.db.database import db, ensure_indexes
from app.db.repositories.platform_repo import PlatformRepository

logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
for noisy_logger in ("pymongo", "urllib3", "httpx", "httpcore", "huggingface_hub", "PIL"):
    logging.getLogger(noisy_logger).setLevel(logging.WARNING)
logger = logging.getLogger("seller_feedback_intelligence")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing MongoDB indexes...")
    try:
        ensure_indexes(db)
        platform_repo = PlatformRepository(db)
        platform_repo.get_or_create("lazada", "Lazada")
        platform_repo.get_or_create("tiki", "Tiki")
        platform_repo.get_or_create("tiktok_shop", "TikTok Shop")
        logger.info("Default platforms verified.")
    except Exception as exc:
        logger.warning("MongoDB is not ready yet: %s", exc)
    yield
    logger.info("Shutting down backend...")
    try:
        from app.services.tiktok_browser_session import close_session

        close_session()
    except Exception as exc:
        logger.debug("TikTok browser session cleanup skipped: %s", exc)
    try:
        from app.services.lazada_browser_session import close_session

        close_session()
    except Exception as exc:
        logger.debug("Lazada browser session cleanup skipped: %s", exc)


app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    description="Hệ thống AI hỗ trợ seller tổng hợp review, kiểm tra bằng chứng ảnh, đánh giá độ tin cậy và ưu tiên xử lý phản hồi.",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error on {request.method} {request.url.path}: {str(exc)}", exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "Internal server error. Please check server logs."})


app.include_router(api_router)


@app.get("/")
def root():
    return {"message": "Welcome to Seller Feedback Intelligence API", "documentation": "/docs", "health": "/api/v1/health"}
