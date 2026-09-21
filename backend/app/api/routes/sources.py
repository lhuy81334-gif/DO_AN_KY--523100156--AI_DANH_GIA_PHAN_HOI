from fastapi import APIRouter

router = APIRouter(prefix="/sources", tags=["Sources & Connectors"])


@router.get("")
def list_available_sources():
    return [
        {
            "code": "csv_json",
            "name": "Real CSV / JSON import",
            "is_active": True,
            "requires_credentials": False,
            "target_data": ["products", "reviews"],
        },
        {
            "code": "tiki_reviews_api",
            "name": "Tiki review API script",
            "is_active": True,
            "requires_credentials": False,
            "script": "scripts/fetch_tiki_reviews.py",
            "folder": "data/api/tiki",
            "target_data": ["reviews"],
        },
        {
            "code": "lazada_reviews_api",
            "name": "Lazada review MTOP script",
            "is_active": True,
            "requires_credentials": True,
            "script": "scripts/fetch_lazada_reviews.py",
            "setup_script": "scripts/configure_lazada_env.py",
            "folder": "data/api/lazada",
            "target_data": ["reviews"],
        },
        {
            "code": "tiktok_shop_reviews_api",
            "name": "TikTok Shop product review API script",
            "is_active": True,
            "requires_credentials": True,
            "script": "scripts/fetch_tiktok_shop_reviews.py",
            "setup_script": "scripts/configure_tiktok_shop_env.py",
            "folder": "data/api/tiktok_shop",
            "target_data": ["reviews"],
        },
    ]
