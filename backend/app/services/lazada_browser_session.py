from __future__ import annotations

import hashlib
import json
import queue
import sys
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from app.config import settings
from scripts import fetch_lazada_reviews


ROOT_DIR = Path(__file__).resolve().parents[3]
DEFAULT_START_URL = "https://www.lazada.vn/"


class LazadaBrowserUnavailable(RuntimeError):
    pass


class LazadaBrowserSessionRequired(RuntimeError):
    pass


_lock = threading.RLock()
_playwright: Any = None
_context: Any = None
_page: Any = None
_worker_thread: threading.Thread | None = None
_worker_thread_id: int | None = None
_worker_tasks: "queue.Queue[tuple[Any, tuple[Any, ...], dict[str, Any], threading.Event, dict[str, Any]]]" = queue.Queue()


def _is_closed_browser_error(exc: BaseException) -> bool:
    message = str(exc).lower()
    return any(
        marker in message
        for marker in (
            "target page, context or browser has been closed",
            "browser has been closed",
            "context has been closed",
            "page has been closed",
        )
    )


def _mark_context_closed(*_: Any) -> None:
    global _context, _page
    _context = None
    _page = None


def _reset_browser_state(stop_playwright: bool = True) -> None:
    global _playwright, _context, _page

    if _context is not None:
        try:
            _context.close()
        except Exception:
            pass
    if stop_playwright and _playwright is not None:
        try:
            _playwright.stop()
        except Exception:
            pass
        _playwright = None

    _context = None
    _page = None


def _prepare_windows_event_loop_policy() -> None:
    if sys.platform != "win32":
        return
    import asyncio

    proactor_policy = getattr(asyncio, "WindowsProactorEventLoopPolicy", None)
    if proactor_policy is None:
        return
    if not isinstance(asyncio.get_event_loop_policy(), proactor_policy):
        asyncio.set_event_loop_policy(proactor_policy())


def _profile_dir() -> Path:
    configured = Path(settings.LAZADA_BROWSER_PROFILE_DIR)
    if configured.is_absolute():
        return configured
    return ROOT_DIR / configured


def _import_playwright():
    _prepare_windows_event_loop_policy()
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise LazadaBrowserUnavailable(
            "Chưa cài Playwright. Chạy: .\\.venv\\Scripts\\pip.exe install playwright; "
            ".\\.venv\\Scripts\\python.exe -m playwright install chromium"
        ) from exc
    return sync_playwright, PlaywrightTimeoutError


def _worker_loop() -> None:
    global _worker_thread_id
    _worker_thread_id = threading.get_ident()
    _prepare_windows_event_loop_policy()
    while True:
        fn, args, kwargs, done, result_box = _worker_tasks.get()
        try:
            result_box["result"] = fn(*args, **kwargs)
        except BaseException as exc:
            result_box["error"] = exc
        finally:
            done.set()


def _ensure_worker() -> None:
    global _worker_thread
    if _worker_thread is not None and _worker_thread.is_alive():
        return
    _worker_thread = threading.Thread(target=_worker_loop, name="lazada-playwright", daemon=True)
    _worker_thread.start()


def _run_on_worker(fn: Any, *args: Any, **kwargs: Any) -> Any:
    if threading.get_ident() == _worker_thread_id:
        return fn(*args, **kwargs)

    _ensure_worker()
    done = threading.Event()
    result_box: dict[str, Any] = {}
    _worker_tasks.put((fn, args, kwargs, done, result_box))
    done.wait()
    if "error" in result_box:
        raise result_box["error"]
    return result_box.get("result")


def _has_active_context() -> bool:
    if _context is None:
        return False
    try:
        _context.pages
        return True
    except Exception:
        _mark_context_closed()
        return False


def _ensure_context(start_url: str = "") -> tuple[Any, Any]:
    global _playwright, _context, _page

    sync_playwright, PlaywrightTimeoutError = _import_playwright()
    profile = _profile_dir()
    profile.mkdir(parents=True, exist_ok=True)

    last_error: BaseException | None = None
    for attempt in range(2):
        try:
            if not _has_active_context():
                _reset_browser_state(stop_playwright=True)
                _playwright = sync_playwright().start()
                _context = _playwright.chromium.launch_persistent_context(
                    user_data_dir=str(profile),
                    headless=settings.LAZADA_BROWSER_HEADLESS,
                    viewport={"width": 1366, "height": 900},
                    locale="vi-VN",
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--disable-dev-shm-usage",
                    ],
                )
                _context.on("close", _mark_context_closed)

            pages = [page for page in _context.pages if not page.is_closed()]
            if _page is None or _page.is_closed() or _page not in pages:
                _page = pages[0] if pages else _context.new_page()

            if start_url:
                try:
                    _page.goto(start_url, wait_until="domcontentloaded", timeout=45000)
                except PlaywrightTimeoutError:
                    pass

            return _context, _page
        except Exception as exc:
            last_error = exc
            _reset_browser_state(stop_playwright=True)
            if attempt == 0 and _is_closed_browser_error(exc):
                continue
            raise

    raise RuntimeError(f"Không mở lại được phiên Lazada: {last_error}") from last_error


def _session_status_internal() -> dict[str, Any]:
    return {
        "available": True,
        "active": _has_active_context(),
        "profile_dir": str(_profile_dir()),
        "message": "Playwright đã sẵn sàng.",
    }


def session_status() -> dict[str, Any]:
    available = True
    message = "Playwright đã sẵn sàng."
    try:
        _import_playwright()
    except LazadaBrowserUnavailable as exc:
        available = False
        message = str(exc)

    active = False
    if available and _worker_thread is not None and _worker_thread.is_alive():
        try:
            active = bool(_run_on_worker(_has_active_context))
        except Exception:
            active = False
    return {
        "available": available,
        "active": active,
        "profile_dir": str(_profile_dir()),
        "message": message,
    }


def _open_login_session_internal(start_url: str = "") -> dict[str, Any]:
    url = start_url or DEFAULT_START_URL
    with _lock:
        _ensure_context(url)
        return {
            **_session_status_internal(),
            "opened": True,
            "message": (
                "Đã mở cửa sổ Lazada. Hãy đăng nhập hoặc giải captcha nếu Lazada yêu cầu, "
                "đợi trang sản phẩm tải xong rồi bấm lại nút Kéo + phân tích đầy đủ."
            ),
        }


def open_login_session(start_url: str = "") -> dict[str, Any]:
    return _run_on_worker(_open_login_session_internal, start_url)


def _close_session_internal() -> dict[str, Any]:
    with _lock:
        _reset_browser_state(stop_playwright=True)
    return {**_session_status_internal(), "message": "Đã đóng phiên trình duyệt Lazada."}


def close_session() -> dict[str, Any]:
    if _worker_thread is None or not _worker_thread.is_alive():
        return {
            "available": True,
            "active": False,
            "profile_dir": str(_profile_dir()),
            "message": "Không có phiên trình duyệt Lazada đang mở.",
        }
    return _run_on_worker(_close_session_internal)


def _cookie_value(name: str) -> str:
    if _context is None:
        return ""
    for cookie in _context.cookies(["https://www.lazada.vn", "https://acs-m.lazada.vn"]):
        if cookie.get("name") == name:
            return str(cookie.get("value") or "")
    return ""


def _mtop_token(product_url: str) -> str:
    token_cookie = _cookie_value("_m_h5_tk")
    if not token_cookie and _context is not None:
        try:
            _context.request.get(
                fetch_lazada_reviews.LAZADA_REVIEW_URL,
                headers={"Referer": product_url or DEFAULT_START_URL, "Origin": "https://www.lazada.vn"},
                timeout=int(settings.LAZADA_MTOP_TIMEOUT_SECONDS * 1000),
            )
        except Exception:
            pass
        token_cookie = _cookie_value("_m_h5_tk")
    return token_cookie.split("_", 1)[0] if token_cookie else ""


def _build_review_params(token: str, item_id: str, page_size: int, page_no: int, star: int, tag_id: int) -> dict[str, str]:
    payload_dict = {
        "itemId": item_id,
        "pageSize": page_size,
        "pageNo": page_no,
        "ratingFilter": star,
        "sort": 0,
        "tagId": tag_id,
    }
    data_str = json.dumps(payload_dict, separators=(",", ":"))
    timestamp_ms = str(int(time.time() * 1000))
    sign = hashlib.md5(f"{token}&{timestamp_ms}&{fetch_lazada_reviews.APP_KEY}&{data_str}".encode("utf-8")).hexdigest()
    return {
        "jsv": "2.7.2",
        "appKey": fetch_lazada_reviews.APP_KEY,
        "t": timestamp_ms,
        "sign": sign,
        "api": fetch_lazada_reviews.API_NAME,
        "v": "1.0",
        "type": "originaljson",
        "isSec": "1",
        "AntiCreep": "true",
        "timeout": "10000",
        "dataType": "json",
        "sessionOption": "AutoLoginOnly",
        "x-i18n-language": "en",
        "x-i18n-regionID": "VN",
        "data": data_str,
    }


def _fetch_review_page(product_url: str, params: dict[str, str]) -> dict[str, Any]:
    if _context is None:
        raise LazadaBrowserSessionRequired("Chưa có phiên trình duyệt Lazada.")
    request_url = f"{fetch_lazada_reviews.LAZADA_REVIEW_URL}?{urlencode(params)}"
    try:
        response = _context.request.post(
            request_url,
            data="",
            headers={
                "Accept": "application/json",
                "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": "https://www.lazada.vn",
                "Referer": product_url or DEFAULT_START_URL,
            },
            timeout=int(settings.LAZADA_MTOP_TIMEOUT_SECONDS * 1000),
        )
        payload = response.json()
        payload["__http_status"] = response.status
        fetch_lazada_reviews.raise_for_lazada_error(payload)
        return payload
    except Exception as exc:
        if _is_closed_browser_error(exc):
            raise LazadaBrowserSessionRequired(
                "Phiên Lazada vừa bị đóng trong lúc kéo review. Hãy bấm Mở phiên sàn rồi chạy lại."
            ) from exc
        raise


def fetch_reviews_with_browser(
    product_url: str,
    item_id: str,
    page_size: int = 5,
    max_pages_per_star: int = 10,
    delay: float = 2.0,
    tag_id: int = 0,
    stars_order: list[int] | None = None,
) -> dict[str, Any]:
    return _run_on_worker(
        _fetch_reviews_with_browser_internal,
        product_url,
        item_id,
        page_size,
        max_pages_per_star,
        delay,
        tag_id,
        stars_order,
    )


def _fetch_reviews_with_browser_internal(
    product_url: str,
    item_id: str,
    page_size: int = 5,
    max_pages_per_star: int = 10,
    delay: float = 2.0,
    tag_id: int = 0,
    stars_order: list[int] | None = None,
) -> dict[str, Any]:
    if not _has_active_context():
        raise LazadaBrowserSessionRequired(
            "Chưa có phiên trình duyệt Lazada. Hãy bấm Mở phiên sàn, đăng nhập nếu cần rồi chạy lại."
        )

    page_size = max(1, min(int(page_size), 5))
    max_pages_per_star = max(1, int(max_pages_per_star))
    stars_list = stars_order or [1, 2, 3, 4, 5]
    all_collected: list[dict[str, Any]] = []
    market_stats: list[dict[str, Any]] = []
    stopped_by_validate = False
    last_error = ""

    with _lock:
        _, page = _ensure_context(product_url or DEFAULT_START_URL)
        page.wait_for_timeout(int(max(settings.LAZADA_BROWSER_READY_WAIT_SECONDS, 0) * 1000))

        for star in stars_list:
            print(f"\n--- Dang vet Lazada bang browser {star} sao ---")
            star_count = 0
            for page_no in range(1, max_pages_per_star + 1):
                token = _mtop_token(product_url)
                if not token:
                    raise LazadaBrowserSessionRequired(
                        "Chưa lấy được token Lazada từ phiên trình duyệt. Hãy đăng nhập/giải captcha xong rồi kéo lại."
                    )

                params = _build_review_params(token, item_id, page_size, page_no, star, tag_id)
                try:
                    response_json = _fetch_review_page(product_url, params)
                    module = response_json.get("data", {}).get("module", {})
                    if not market_stats and "impressionTags" in module:
                        market_stats = module.get("impressionTags", [])

                    reviews = module.get("reviews", [])
                    if not reviews:
                        print(f"  [i] Da het review cho muc {star} sao.")
                        break

                    sample_label = "HIGH_RATING" if star >= 4 else "LOW_RATING"
                    if star == 3:
                        sample_label = "NEUTRAL_RATING"
                    for review in reviews:
                        all_collected.append(fetch_lazada_reviews.normalize_lazada_review(review, item_id, sample_label))

                    print(f"  [+] {star} sao - Trang {page_no}: nhan {len(reviews)} review (Luy ke: {len(all_collected)})")
                    star_count += len(reviews)
                    if delay > 0:
                        time.sleep(delay)
                except Exception as exc:
                    last_error = fetch_lazada_reviews.safe_error_text(exc)
                    print(f"  [!] Loi tai trang {page_no}: {last_error}")
                    if fetch_lazada_reviews.is_user_validate_error(exc):
                        stopped_by_validate = True
                        if not all_collected and star_count == 0:
                            raise LazadaBrowserSessionRequired(
                                "Lazada đang yêu cầu xác minh phiên trình duyệt. Hãy đăng nhập/giải captcha rồi kéo lại."
                            ) from exc
                        return _build_output(all_collected, market_stats, stopped_by_validate, last_error)
                    break

    return _build_output(all_collected, market_stats, stopped_by_validate, last_error)


def _build_output(
    reviews: list[dict[str, Any]],
    market_stats: list[dict[str, Any]],
    stopped_by_validate: bool,
    last_error: str,
) -> dict[str, Any]:
    reviews.sort(key=fetch_lazada_reviews.review_timestamp, reverse=True)
    print("\n" + "=" * 45)
    print(f"Hoan tat bang browser! Tong cong thu duoc {len(reviews)} review tren Lazada.")
    return {
        "market_statistics": market_stats,
        "collected_count": len(reviews),
        "reviews": reviews,
        "stopped_by_validate": stopped_by_validate,
        "last_error": last_error,
    }
