import re
import sys
import logging
from typing import Optional
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from pymongo.database import Database

from app.db.database import get_db, utcnow
from app.db.repositories.platform_repo import PlatformRepository
from app.db.repositories.product_repo import ProductRepository
from app.ingestion.json_importer import JSONImporter
from app.ml.image_evidence import analyze_review_image_relevance
from app.ml.review_trust import analyze_review_trust
from app.config import settings
from app.services.product_metadata import update_product_metadata_from_url
from app.services.seller_feedback import SellerFeedbackService

ROOT_DIR = Path(__file__).resolve().parents[4]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

router = APIRouter(prefix="/seller-feedback", tags=["Seller Feedback"])
logger = logging.getLogger("seller_feedback_intelligence")


class ProductLinkRequest(BaseModel):
    product_url: str


class ProductLinkIngestRequest(ProductLinkRequest):
    page_size: int = 20
    max_pages_per_star: int = 50
    delay: float = 0.2


class TikTokBrowserSessionRequest(BaseModel):
    product_url: Optional[str] = None


class ProductImageAnalysisRequest(BaseModel):
    product_url: Optional[str] = None
    platform_code: Optional[str] = None
    external_product_id: Optional[str] = None
    product_id: Optional[int] = None
    limit: int = 0
    max_images_per_review: int = 2


def _first_query_value(query: dict[str, list[str]], *keys: str) -> str:
    for key in keys:
        values = query.get(key)
        if values and values[0]:
            return values[0].strip()
    return ""


def _canonical_product_url(platform_code: str, external_product_id: str, spid: str = "") -> str:
    if platform_code == "lazada":
        return f"https://www.lazada.vn/products/i{external_product_id}.html"
    if platform_code == "tiki":
        suffix = f"?spid={spid}" if spid else ""
        return f"https://tiki.vn/product-p{external_product_id}.html{suffix}"
    if platform_code == "tiktok_shop":
        return f"https://shop.tiktok.com/vn/pdp/{external_product_id}"
    return ""


def _product_preview_images(product: dict | None) -> list[str]:
    if not product:
        return []
    images = product.get("product_images") or product.get("images") or product.get("image_urls") or []
    return [str(url) for url in images if isinstance(url, str) and url.strip()]


def _ensure_product_for_link(db: Database, platform_code: str, external_product_id: str, product_url: str) -> dict:
    platform = PlatformRepository(db).get_or_create(platform_code, platform_code.capitalize())
    title = f"{platform_code.capitalize()} product {external_product_id}"
    product_repo = ProductRepository(db)
    existing = product_repo.get_by_external_id(platform.id, external_product_id)
    if not existing:
        product_repo.bulk_upsert_products(
            [
                {
                    "platform_id": platform.id,
                    "external_product_id": external_product_id,
                    "title": title,
                    "normalized_title": title.lower(),
                    "description": "",
                    "category": "",
                    "product_url": product_url,
                }
            ]
        )
    elif product_url:
        db.products.update_one(
            {"platform_id": platform.id, "external_product_id": external_product_id},
            {"$set": {"product_url": product_url}},
        )
    return db.products.find_one({"platform_id": platform.id, "external_product_id": external_product_id}, {"_id": 0}) or {}


def _analyze_trust_for_product(db: Database, product_id: int) -> int:
    now = utcnow()
    total = 0
    for review in db.reviews.find({"product_id": product_id}):
        analysis = analyze_review_trust(review)
        db.reviews.update_one(
            {"_id": review["_id"]},
            {"$set": {"trust_analysis": analysis, "trust_analyzed_at": now}},
        )
        db.review_trust_analyses.update_one(
            {"review_id": review["id"]},
            {
                "$set": {
                    "review_id": review["id"],
                    "product_id": review["product_id"],
                    "platform_code": review.get("platform_code", ""),
                    "source": review.get("source", ""),
                    "external_product_id": review.get("external_product_id", ""),
                    "product_title": review.get("product_title", ""),
                    "analysis": analysis,
                    "updated_at": now,
                }
            },
            upsert=True,
        )
        total += 1
    return total


def _analyze_images_for_product(
    db: Database,
    product_id: int,
    max_images_per_review: int = 2,
    limit: int = 0,
) -> dict:
    now = utcnow()
    product = db.products.find_one({"id": product_id}, {"_id": 0})
    preview_images = _product_preview_images(product)
    logger.info(
        "Image comparison product_id=%s product_images_found=%s first_product_image=%s",
        product_id,
        len(preview_images),
        preview_images[0] if preview_images else "",
    )
    query = {
        "product_id": product_id,
        "$or": [
            {"images.0": {"$exists": True}},
            {"review_images.0": {"$exists": True}},
            {"image_urls.0": {"$exists": True}},
        ],
    }
    total = 0
    failed = 0
    last_error = ""

    cursor = db.reviews.find(query).sort("created_at", -1)
    if limit > 0:
        cursor = cursor.limit(limit)

    for review in cursor:
        try:
            result = analyze_review_image_relevance(
                review,
                product=product,
                max_images=max_images_per_review,
            )
            if result["images_analyzed"] == 0:
                failed += 1

            db.reviews.update_one(
                {"_id": review["_id"]},
                {
                    "$set": {
                        "image_evidence": result,
                        "image_relevance_score": result["image_relevance_score"],
                        "image_analyzed_at": now,
                    }
                },
            )

            updated_review = dict(review)
            updated_review["image_relevance_score"] = result["image_relevance_score"]
            updated_review["image_evidence_status"] = result["image_evidence_status"]
            updated_review["claim_evidence_status"] = result.get("claim_evidence_status")
            updated_review["claim_evidence_score"] = result.get("claim_evidence_score")
            trust = analyze_review_trust(updated_review)
            db.reviews.update_one(
                {"_id": review["_id"]},
                {"$set": {"trust_analysis": trust, "trust_analyzed_at": now}},
            )
            db.review_trust_analyses.update_one(
                {"review_id": review["id"]},
                {
                    "$set": {
                        "review_id": review["id"],
                        "product_id": review["product_id"],
                        "platform_code": review.get("platform_code", ""),
                        "source": review.get("source", ""),
                        "external_product_id": review.get("external_product_id", ""),
                        "product_title": review.get("product_title", ""),
                        "analysis": trust,
                        "updated_at": now,
                    }
                },
                upsert=True,
            )
            total += 1
        except Exception as exc:
            failed += 1
            last_error = str(exc)

    return {"image_reviews_analyzed": total, "image_reviews_failed": failed, "last_error": last_error}


def _product_from_analysis_request(db: Database, payload: ProductImageAnalysisRequest) -> tuple[dict, dict]:
    metadata_result = {"images_found": 0, "product_images": [], "error": ""}
    product_url = (payload.product_url or "").strip()

    if product_url:
        resolved = _resolve_product_url(product_url)
        platform_code = resolved["platform_code"]
        external_product_id = resolved["external_product_id"]
        canonical_url = (
            product_url
            if platform_code == "tiktok_shop"
            else _canonical_product_url(platform_code, external_product_id, resolved.get("spid", ""))
        )
        product = _ensure_product_for_link(db, platform_code, external_product_id, canonical_url)
        try:
            metadata_result = update_product_metadata_from_url(
                db,
                platform_code,
                external_product_id,
                canonical_url,
                fetch_url=product_url,
            )
        except Exception as exc:
            metadata_result["error"] = str(exc)
        if product.get("id"):
            product = db.products.find_one({"id": int(product["id"])}, {"_id": 0}) or product
        product["platform_code"] = platform_code
        return product, metadata_result

    if payload.product_id is not None:
        product = db.products.find_one({"id": payload.product_id}, {"_id": 0})
        if product:
            platform = db.platforms.find_one({"id": product.get("platform_id")}, {"_id": 0, "code": 1})
            product["platform_code"] = (platform or {}).get("code", "")
            return product, metadata_result

    if payload.platform_code and payload.external_product_id:
        platform = PlatformRepository(db).get_by_code(payload.platform_code)
        if platform:
            product = db.products.find_one(
                {"platform_id": platform.id, "external_product_id": str(payload.external_product_id)},
                {"_id": 0},
            )
            if product:
                product["platform_code"] = payload.platform_code
                return product, metadata_result

    raise HTTPException(status_code=404, detail="Chưa tìm thấy sản phẩm trong Mongo để phân tích ảnh.")


def _resolve_product_url(product_url: str) -> dict:
    parsed = urlparse(product_url.strip())
    host = parsed.netloc.lower()
    path = unquote(parsed.path)
    query = parse_qs(parsed.query)

    if "lazada.vn" in host:
        path_match = re.search(r"i(\d+)(?:-|\.html|$)", path)
        path_item_id = path_match.group(1) if path_match else ""
        query_item_id = _first_query_value(query, "itemId", "item_id")
        tracking_item_id = _first_query_value(query, "pdp_item")
        external_product_id = path_item_id or query_item_id or tracking_item_id
        if not external_product_id:
            raise HTTPException(status_code=400, detail="Không tìm thấy Lazada itemId trong link.")
        candidates = {
            "path_item_id": path_item_id,
            "query_item_id": query_item_id,
            "tracking_pdp_item": tracking_item_id,
        }
        return {
            "platform_code": "lazada",
            "external_product_id": external_product_id,
            "spid": "",
            "detected_from": "path_item_id" if path_item_id else "query_item_id" if query_item_id else "tracking_pdp_item",
            "candidate_product_ids": {key: value for key, value in candidates.items() if value},
        }

    if "tiki.vn" in host:
        path_match = re.search(r"(?:-|/)p(\d+)\.html", path)
        path_product_id = path_match.group(1) if path_match else ""
        query_product_id = _first_query_value(query, "product_id", "productId")
        spid = _first_query_value(query, "spid", "seller_product_id", "sellerProductId")
        external_product_id = path_product_id or query_product_id
        if not external_product_id:
            raise HTTPException(status_code=400, detail="Không tìm thấy Tiki product_id trong link.")
        return {
            "platform_code": "tiki",
            "external_product_id": external_product_id,
            "spid": spid,
            "detected_from": "path_product_id" if path_product_id else "query_product_id",
            "candidate_product_ids": {
                key: value
                for key, value in {"path_product_id": path_product_id, "query_product_id": query_product_id, "spid": spid}.items()
                if value
            },
        }

    if "shop.tiktok.com" in host:
        path_match = re.search(r"/pdp/(?:[^/]+/)?(\d+)", path)
        path_product_id = path_match.group(1) if path_match else ""
        query_product_id = _first_query_value(query, "product_id", "productId")
        external_product_id = path_product_id or query_product_id
        if not external_product_id:
            raise HTTPException(status_code=400, detail="Không tìm thấy TikTok Shop product_id trong link.")
        return {
            "platform_code": "tiktok_shop",
            "external_product_id": external_product_id,
            "spid": "",
            "detected_from": "path_product_id" if path_product_id else "query_product_id",
            "candidate_product_ids": {
                key: value
                for key, value in {"path_product_id": path_product_id, "query_product_id": query_product_id}.items()
                if value
            },
        }

    raise HTTPException(status_code=400, detail="Hiện chỉ hỗ trợ link Lazada, Tiki hoặc TikTok Shop.")


@router.post("/resolve-product-link")
def resolve_product_link(payload: ProductLinkRequest, db: Database = Depends(get_db)):
    resolved = _resolve_product_url(payload.product_url)
    platform = PlatformRepository(db).get_by_code(resolved["platform_code"])
    product = None
    if platform:
        product = db.products.find_one(
            {"platform_id": platform.id, "external_product_id": resolved["external_product_id"]},
            {"_id": 0, "id": 1, "title": 1, "product_url": 1, "product_images": 1, "images": 1, "image_urls": 1},
        )

    review_query = {
        "platform_code": resolved["platform_code"],
        "external_product_id": resolved["external_product_id"],
    }
    total_reviews = db.reviews.count_documents(review_query)
    total_images = db.reviews.count_documents({**review_query, "image_urls.0": {"$exists": True}})
    product_url = (product or {}).get("product_url") or _canonical_product_url(
        resolved["platform_code"],
        resolved["external_product_id"],
        resolved.get("spid", ""),
    )
    has_data = total_reviews > 0

    return {
        **resolved,
        "product_id": (product or {}).get("id"),
        "product_title": (product or {}).get("title", ""),
        "product_url": product_url,
        "product_images": _product_preview_images(product),
        "images_found": len(_product_preview_images(product)),
        "has_data": has_data,
        "total_reviews": total_reviews,
        "total_reviews_with_images": total_images,
        "message": (
            f"Đã tìm thấy {total_reviews} review trong Mongo cho sản phẩm này."
            if has_data
            else "Đã nhận diện được sản phẩm, nhưng Mongo chưa có review. Cần chạy bước kéo API trước khi phân tích."
        ),
    }


@router.get("/tiktok/session")
def get_tiktok_browser_session():
    try:
        from app.services.tiktok_browser_session import session_status

        return session_status()
    except Exception as exc:
        detail = str(exc) or repr(exc)
        raise HTTPException(status_code=400, detail=detail) from exc


@router.post("/tiktok/session/open")
def open_tiktok_browser_session(payload: TikTokBrowserSessionRequest):
    start_url = (payload.product_url or "").strip() or "https://shop.tiktok.com/"
    if start_url != "https://shop.tiktok.com/":
        resolved = _resolve_product_url(start_url)
        if resolved["platform_code"] != "tiktok_shop":
            raise HTTPException(status_code=400, detail="Nút này chỉ dùng cho link TikTok Shop.")
    try:
        from app.services.tiktok_browser_session import open_login_session

        return open_login_session(start_url)
    except Exception as exc:
        detail = str(exc) or repr(exc)
        raise HTTPException(status_code=400, detail=detail) from exc


@router.post("/tiktok/session/close")
def close_tiktok_browser_session():
    try:
        from app.services.tiktok_browser_session import close_session

        return close_session()
    except Exception as exc:
        detail = str(exc) or repr(exc)
        raise HTTPException(status_code=400, detail=detail) from exc


@router.get("/lazada/session")
def get_lazada_browser_session():
    try:
        from app.services.lazada_browser_session import session_status

        return session_status()
    except Exception as exc:
        detail = str(exc) or repr(exc)
        raise HTTPException(status_code=400, detail=detail) from exc


@router.post("/lazada/session/open")
def open_lazada_browser_session(payload: TikTokBrowserSessionRequest):
    start_url = (payload.product_url or "").strip() or "https://www.lazada.vn/"
    if start_url != "https://www.lazada.vn/":
        resolved = _resolve_product_url(start_url)
        if resolved["platform_code"] != "lazada":
            raise HTTPException(status_code=400, detail="Nút này chỉ dùng cho link Lazada.")
    try:
        from app.services.lazada_browser_session import open_login_session

        return open_login_session(start_url)
    except Exception as exc:
        detail = str(exc) or repr(exc)
        raise HTTPException(status_code=400, detail=detail) from exc


@router.post("/lazada/session/close")
def close_lazada_browser_session():
    try:
        from app.services.lazada_browser_session import close_session

        return close_session()
    except Exception as exc:
        detail = str(exc) or repr(exc)
        raise HTTPException(status_code=400, detail=detail) from exc


@router.post("/ingest-product-link")
def ingest_product_link(payload: ProductLinkIngestRequest, db: Database = Depends(get_db)):
    resolved = _resolve_product_url(payload.product_url)
    platform_code = resolved["platform_code"]
    external_product_id = resolved["external_product_id"]
    original_product_url = payload.product_url.strip()
    product_url = (
        original_product_url
        if platform_code == "tiktok_shop"
        else _canonical_product_url(platform_code, external_product_id, resolved.get("spid", ""))
    )
    product = _ensure_product_for_link(db, platform_code, external_product_id, product_url)
    product_metadata = {"images_found": 0, "product_images": [], "error": ""}
    try:
        product_metadata = update_product_metadata_from_url(
            db,
            platform_code,
            external_product_id,
            product_url,
            fetch_url=original_product_url,
        )
        logger.info(
            "Product metadata product=%s platform=%s product_images_found=%s first_product_image=%s",
            external_product_id,
            platform_code,
            product_metadata.get("images_found", 0),
            (product_metadata.get("product_images") or [""])[0],
        )
    except Exception as exc:
        product_metadata["error"] = str(exc)

    source_mode = "request"
    try:
        if platform_code == "lazada":
            from scripts import fetch_lazada_reviews

            lazada_page_size = min(payload.page_size, 5)
            lazada_max_pages = min(
                max(payload.max_pages_per_star, 1),
                max(settings.LAZADA_INGEST_MAX_PAGES_PER_STAR, 1),
            )
            lazada_delay = max(payload.delay, settings.LAZADA_INGEST_DELAY_SECONDS)
            lazada_stars_order = [1, 2, 3, 4, 5] if settings.LAZADA_INGEST_LOW_RATING_FIRST else [5, 4, 3, 2, 1]
            logger.info(
                "Starting Lazada ingest product=%s page_size=%s max_pages_per_star=%s delay=%s stars_order=%s",
                external_product_id,
                lazada_page_size,
                lazada_max_pages,
                lazada_delay,
                lazada_stars_order,
            )
            output_data = None
            browser_error = ""
            if settings.LAZADA_USE_BROWSER_SESSION:
                try:
                    from app.services.lazada_browser_session import (
                        LazadaBrowserSessionRequired,
                        fetch_reviews_with_browser,
                        open_login_session,
                    )

                    output_data = fetch_reviews_with_browser(
                        product_url=original_product_url,
                        item_id=external_product_id,
                        page_size=lazada_page_size,
                        max_pages_per_star=lazada_max_pages,
                        delay=lazada_delay,
                        stars_order=lazada_stars_order,
                    )
                    source_mode = "browser_session"
                    logger.info("Lazada browser ingest collected %s reviews", output_data.get("collected_count", 0))
                except LazadaBrowserSessionRequired as exc:
                    open_login_session(original_product_url)
                    raise RuntimeError(
                        "Lazada cần đăng nhập/xác minh phiên trình duyệt. "
                        "Mình đã mở cửa sổ Lazada; hãy đăng nhập hoặc giải captcha nếu cần, đợi trang sản phẩm tải xong rồi bấm lại Kéo + phân tích đầy đủ."
                    ) from exc
                except Exception as exc:
                    browser_error = str(exc)
                    logger.warning("Lazada browser ingest failed: %s", browser_error)

            if output_data is None:
                try:
                    output_data = fetch_lazada_reviews.fetch_all_lazada_reviews(
                        item_id=external_product_id,
                        page_size=lazada_page_size,
                        max_pages_per_star=lazada_max_pages,
                        delay=lazada_delay,
                        stars_order=lazada_stars_order,
                    )
                except RuntimeError as exc:
                    if browser_error:
                        raise RuntimeError(
                            f"Lazada API error: phiên trình duyệt chưa dùng được ({browser_error}); "
                            f"request dự phòng cũng lỗi ({exc})"
                        ) from exc
                    raise
            if output_data.get("stopped_by_validate") and not output_data.get("collected_count"):
                raise RuntimeError("LAZADA_USER_VALIDATE")
            raw_path = fetch_lazada_reviews.OUTPUT_DIR / f"all_lazada_reviews_{external_product_id}.json"
            normalized_path = fetch_lazada_reviews.OUTPUT_DIR / f"all_lazada_reviews_{external_product_id}_normalized.json"
            fetch_lazada_reviews.save_json(output_data, raw_path)
            normalized = fetch_lazada_reviews.to_import_schema(output_data, external_product_id=external_product_id)
            fetch_lazada_reviews.save_json(normalized, normalized_path)
            stats = JSONImporter(db).import_reviews_file(str(normalized_path), platform_code="lazada")
            source_reviews = output_data.get("collected_count", 0)
            normalized_reviews = len(normalized)
        elif platform_code == "tiki":
            from scripts import fetch_tiki_reviews

            spid = resolved.get("spid") or external_product_id
            reviews = fetch_tiki_reviews.fetch_all_reviews_by_stars(
                product_id=external_product_id,
                spid=spid,
                page_size=payload.page_size,
                max_pages_per_star=payload.max_pages_per_star,
                delay=payload.delay,
            )
            raw_path = fetch_tiki_reviews.OUTPUT_DIR / f"all_stratified_reviews_{external_product_id}.json"
            normalized_path = fetch_tiki_reviews.OUTPUT_DIR / f"all_stratified_reviews_{external_product_id}_normalized.json"
            fetch_tiki_reviews.save_json(reviews, raw_path)
            normalized = fetch_tiki_reviews.normalize_tiki_reviews(reviews, external_product_id=external_product_id)
            fetch_tiki_reviews.save_json(normalized, normalized_path)
            stats = JSONImporter(db).import_reviews_file(str(normalized_path), platform_code="tiki")
            source_reviews = len(reviews)
            normalized_reviews = len(normalized)
        else:
            from scripts import fetch_tiktok_shop_reviews

            reviews = []
            browser_error = ""
            tiktok_page_size = min(max(payload.page_size, 1), 20)
            tiktok_max_pages = min(
                max(payload.max_pages_per_star, 1),
                max(settings.TIKTOK_SHOP_INGEST_MAX_PAGES_PER_STAR, 1),
            )
            tiktok_delay = max(payload.delay, settings.TIKTOK_SHOP_INGEST_DELAY_SECONDS)
            logger.info(
                "Starting TikTok Shop ingest product=%s page_size=%s max_pages_per_star=%s delay=%s",
                external_product_id,
                tiktok_page_size,
                tiktok_max_pages,
                tiktok_delay,
            )
            if settings.TIKTOK_SHOP_USE_BROWSER_SESSION:
                try:
                    from app.services.tiktok_browser_session import (
                        TikTokBrowserSessionRequired,
                        fetch_reviews_with_browser,
                        open_login_session,
                    )

                    reviews = fetch_reviews_with_browser(
                        product_url=original_product_url,
                        product_id=external_product_id,
                        page_size=tiktok_page_size,
                        max_pages_per_star=tiktok_max_pages,
                        delay=tiktok_delay,
                    )
                    source_mode = "browser_session"
                    logger.info("TikTok Shop browser ingest collected %s reviews", len(reviews))
                except TikTokBrowserSessionRequired as exc:
                    open_login_session(original_product_url)
                    try:
                        reviews = fetch_reviews_with_browser(
                            product_url=original_product_url,
                            product_id=external_product_id,
                            page_size=tiktok_page_size,
                            max_pages_per_star=tiktok_max_pages,
                            delay=tiktok_delay,
                        )
                        source_mode = "browser_session"
                        logger.info("TikTok Shop browser ingest collected %s reviews after reopening session", len(reviews))
                    except Exception as retry_exc:
                        raise RuntimeError(
                            "TikTok Shop cần đăng nhập/xác minh phiên trình duyệt. "
                            "Mình đã mở lại cửa sổ TikTok Shop; hãy đăng nhập nếu cần rồi bấm lại Kéo + phân tích đầy đủ."
                        ) from retry_exc
                except Exception as exc:
                    browser_error = str(exc)
                    logger.warning("TikTok Shop browser ingest failed: %s", browser_error)

            if not reviews:
                try:
                    reviews = fetch_tiktok_shop_reviews.fetch_reviews_by_stars(
                        product_id=external_product_id,
                        page_size=tiktok_page_size,
                        max_pages_per_star=tiktok_max_pages,
                        delay=tiktok_delay,
                        referer=original_product_url,
                    )
                    logger.info("TikTok Shop request fallback collected %s reviews", len(reviews))
                except RuntimeError as exc:
                    if browser_error:
                        raise RuntimeError(
                            f"TikTok Shop API error: phiên trình duyệt chưa dùng được ({browser_error}); "
                            f"request dự phòng cũng lỗi ({exc})"
                        ) from exc
                    raise
            raw_path = fetch_tiktok_shop_reviews.OUTPUT_DIR / f"all_tiktok_shop_reviews_{external_product_id}.json"
            normalized_path = fetch_tiktok_shop_reviews.OUTPUT_DIR / f"all_tiktok_shop_reviews_{external_product_id}_normalized.json"
            fetch_tiktok_shop_reviews.save_json(reviews, raw_path)
            normalized = fetch_tiktok_shop_reviews.normalize_tiktok_reviews(reviews, external_product_id=external_product_id)
            fetch_tiktok_shop_reviews.save_json(normalized, normalized_path)
            stats = JSONImporter(db).import_reviews_file(str(normalized_path), platform_code="tiktok_shop")
            source_reviews = len(reviews)
            normalized_reviews = len(normalized)
    except RuntimeError as exc:
        message = str(exc)
        if "LAZADA_TOKEN_EXPIRED" in message:
            message = "Cookie/token Lazada đã hết hạn. Hãy Copy as cURL request review mới rồi cấu hình lại LAZADA_MTOP_COOKIE."
        elif "LAZADA_USER_VALIDATE" in message:
            message = (
                "Lazada đang yêu cầu xác minh/chống bot với session hiện tại. "
                "Hãy bấm Mở phiên sàn, đăng nhập/giải captcha nếu có, đợi trang sản phẩm tải xong rồi bấm lại Kéo + phân tích đầy đủ."
            )
        elif "Lazada cần đăng nhập" in message:
            message = str(exc)
        elif "Lazada API error" in message:
            message = (
                "Lazada chưa kéo được review từ session hiện tại. "
                "Hãy bấm Mở phiên sàn, đăng nhập/xác minh nếu Lazada yêu cầu, đợi trang sản phẩm tải xong rồi kéo lại."
            )
        if platform_code == "lazada" and (
            "Lazada cần đăng nhập" in message
            or "Lazada đang yêu cầu xác minh" in message
            or "Lazada chưa kéo được review" in message
        ):
            review_query = {"platform_code": platform_code, "external_product_id": external_product_id}
            return {
                **resolved,
                "status": "needs_browser_session",
                "requires_browser_session": True,
                "product_id": product.get("id"),
                "product_url": product_url,
                "source_reviews": 0,
                "normalized_reviews": 0,
                "import_stats": {"total_rows": 0, "inserted": 0, "updated": 0, "duplicated": 0, "failed": 0},
                "product_metadata": product_metadata,
                "analyzed_reviews": 0,
                "total_reviews": db.reviews.count_documents(review_query),
                "total_reviews_with_images": db.reviews.count_documents({**review_query, "image_urls.0": {"$exists": True}}),
                "image_analysis": {"image_reviews_analyzed": 0, "image_reviews_failed": 0, "last_error": ""},
                "source_mode": "browser_session",
                "message": message,
            }
        if "TikTok Shop API error" in message:
            message = (
                "TikTok Shop chưa kéo được review từ session hiện tại. "
                "Hãy bấm Mở phiên TikTok, đăng nhập/xác minh nếu TikTok yêu cầu, đợi trang sản phẩm tải xong rồi kéo lại."
            )
        elif "TikTok Shop cần đăng nhập" in message:
            message = str(exc)
        raise HTTPException(status_code=400, detail=message) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Chưa kéo được API review từ link này: {exc}") from exc

    product = db.products.find_one({"id": product.get("id")}, {"_id": 0}) if product.get("id") else None
    product = product or _ensure_product_for_link(db, platform_code, external_product_id, product_url)
    analyzed_reviews = _analyze_trust_for_product(db, int(product["id"])) if product.get("id") else 0
    review_query = {"platform_code": platform_code, "external_product_id": external_product_id}
    total_reviews_with_images = db.reviews.count_documents({**review_query, "image_urls.0": {"$exists": True}})
    image_analysis = {"image_reviews_analyzed": 0, "image_reviews_failed": 0, "last_error": ""}
    if product.get("id") and total_reviews_with_images:
        image_limit = 0
        if platform_code == "tiktok_shop":
            image_limit = settings.TIKTOK_SHOP_INGEST_IMAGE_ANALYSIS_LIMIT
        elif platform_code == "lazada":
            image_limit = settings.LAZADA_INGEST_IMAGE_ANALYSIS_LIMIT
        logger.info(
            "Starting image analysis product=%s platform=%s limit=%s",
            product.get("id"),
            platform_code,
            image_limit,
        )
        image_analysis = _analyze_images_for_product(db, int(product["id"]), limit=image_limit)

    return {
        **resolved,
        "product_id": product.get("id"),
        "product_url": product_url,
        "source_reviews": source_reviews,
        "normalized_reviews": normalized_reviews,
        "import_stats": stats,
        "product_metadata": product_metadata,
        "analyzed_reviews": analyzed_reviews,
        "total_reviews": db.reviews.count_documents(review_query),
        "total_reviews_with_images": total_reviews_with_images,
        "image_analysis": image_analysis,
        "source_mode": source_mode,
        "message": "Đã kéo API review, lưu ảnh gốc sản phẩm, phân tích ảnh review và tính lại độ tin cậy.",
    }


@router.post("/analyze-images")
def analyze_product_images(payload: ProductImageAnalysisRequest, db: Database = Depends(get_db)):
    product, product_metadata = _product_from_analysis_request(db, payload)
    product_id = product.get("id")
    if not product_id:
        raise HTTPException(status_code=404, detail="Sản phẩm chưa có id nội bộ để phân tích ảnh.")

    image_query = {
        "product_id": int(product_id),
        "$or": [
            {"images.0": {"$exists": True}},
            {"review_images.0": {"$exists": True}},
            {"image_urls.0": {"$exists": True}},
        ],
    }
    total_reviews_with_images = db.reviews.count_documents(image_query)
    if total_reviews_with_images == 0:
        return {
            "product_id": product_id,
            "platform_code": product.get("platform_code", payload.platform_code or ""),
            "external_product_id": product.get("external_product_id", payload.external_product_id or ""),
            "product_metadata": product_metadata,
            "total_reviews_with_images": 0,
            "image_analysis": {"image_reviews_analyzed": 0, "image_reviews_failed": 0, "last_error": ""},
            "message": "Sản phẩm này chưa có review có ảnh để phân tích.",
        }

    image_analysis = _analyze_images_for_product(
        db,
        int(product_id),
        max_images_per_review=payload.max_images_per_review,
        limit=payload.limit,
    )
    return {
        "product_id": product_id,
        "platform_code": product.get("platform_code", payload.platform_code or ""),
        "external_product_id": product.get("external_product_id", payload.external_product_id or ""),
        "product_metadata": product_metadata,
        "total_reviews_with_images": total_reviews_with_images,
        "image_analysis": image_analysis,
        "message": "Đã phân tích ảnh review và tính lại độ tin cậy bằng điểm ảnh thật.",
    }


@router.get("/summary")
def get_feedback_summary(
    product_id: Optional[int] = Query(None),
    platform_code: Optional[str] = Query(None),
    external_product_id: Optional[str] = Query(None),
    db: Database = Depends(get_db),
):
    return SellerFeedbackService(db).product_feedback_summary(
        product_id=product_id,
        platform_code=platform_code,
        external_product_id=external_product_id,
    )


@router.get("/reviews")
def get_review_decisions(
    product_id: Optional[int] = Query(None),
    platform_code: Optional[str] = Query(None),
    external_product_id: Optional[str] = Query(None),
    rating: Optional[int] = Query(None, ge=1, le=5),
    only_attention: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    db: Database = Depends(get_db),
):
    return SellerFeedbackService(db).list_review_decisions(
        product_id=product_id,
        platform_code=platform_code,
        external_product_id=external_product_id,
        rating=rating,
        only_attention=only_attention,
        limit=limit,
    )


@router.get("/image-comparisons")
def get_image_comparisons(
    product_id: Optional[int] = Query(None),
    platform_code: Optional[str] = Query(None),
    external_product_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: Database = Depends(get_db),
):
    return SellerFeedbackService(db).list_image_comparisons(
        product_id=product_id,
        platform_code=platform_code,
        external_product_id=external_product_id,
        limit=limit,
    )
