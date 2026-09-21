from fastapi import APIRouter
from app.api.routes import (
    health,
    platforms,
    shops,
    products,
    reviews,
    datasets,
    sources,
    seller_feedback,
)

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(health.router)
api_router.include_router(platforms.router)
api_router.include_router(shops.router)
api_router.include_router(products.router)
api_router.include_router(reviews.router)
api_router.include_router(datasets.router)
api_router.include_router(sources.router)
api_router.include_router(seller_feedback.router)
