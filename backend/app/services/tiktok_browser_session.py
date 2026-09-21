from __future__ import annotations

import threading
import time
import queue
from pathlib import Path
from typing import Any
from urllib.parse import quote
import sys
from datetime import datetime

from app.config import settings


ROOT_DIR = Path(__file__).resolve().parents[3]
DEFAULT_REVIEW_URL = "https://shop.tiktok.com/api/shop/pdp_desktop/get_product_reviews"


class TikTokBrowserUnavailable(RuntimeError):
    pass


class TikTokBrowserSessionRequired(RuntimeError):
    pass


_lock = threading.RLock()
_playwright: Any = None
_context: Any = None
_page: Any = None
_last_review_api_url = ""
_worker_thread: threading.Thread | None = None
_worker_tasks: "queue.Queue[tuple[Any, tuple[Any, ...], dict[str, Any], threading.Event, dict[str, Any]]]" = queue.Queue()
_worker_thread_id: int | None = None


def _review_timestamp(review: dict[str, Any]) -> float:
    value = review.get("review_time")
    if value is None or value == "":
        return 0.0
    try:
        timestamp = float(value)
        if timestamp > 10_000_000_000:
            timestamp = timestamp / 1000
        return timestamp
    except (TypeError, ValueError):
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
        except ValueError:
            return 0.0


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
    global _context, _page, _last_review_api_url
    _context = None
    _page = None
    _last_review_api_url = ""


def _reset_browser_state(stop_playwright: bool = True) -> None:
    global _playwright, _context, _page, _last_review_api_url

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
    _last_review_api_url = ""


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
    configured = Path(settings.TIKTOK_SHOP_BROWSER_PROFILE_DIR)
    if configured.is_absolute():
        return configured
    return ROOT_DIR / configured


def _import_playwright():
    _prepare_windows_event_loop_policy()
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise TikTokBrowserUnavailable(
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
    _worker_thread = threading.Thread(target=_worker_loop, name="tiktok-shop-playwright", daemon=True)
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
                    headless=settings.TIKTOK_SHOP_BROWSER_HEADLESS,
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

    raise RuntimeError(f"Không mở lại được phiên TikTok Shop: {last_error}") from last_error


def _session_status_internal() -> dict[str, Any]:
    profile = _profile_dir()
    return {
        "available": True,
        "active": _has_active_context(),
        "profile_dir": str(profile),
        "message": "Playwright đã sẵn sàng.",
    }


def session_status() -> dict[str, Any]:
    available = True
    message = "Playwright đã sẵn sàng."
    try:
        _import_playwright()
    except TikTokBrowserUnavailable as exc:
        available = False
        message = str(exc)

    profile = _profile_dir()
    active = False
    if available and _worker_thread is not None and _worker_thread.is_alive():
        try:
            active = bool(_run_on_worker(_has_active_context))
        except Exception:
            active = False
    return {
        "available": available,
        "active": active,
        "profile_dir": str(profile),
        "message": message,
    }


def _open_login_session_internal(start_url: str = "") -> dict[str, Any]:
    url = start_url or "https://shop.tiktok.com/"
    with _lock:
        _ensure_context(url)
        return {
            **_session_status_internal(),
            "opened": True,
            "message": (
                "Đã mở cửa sổ TikTok Shop. Hãy đăng nhập nếu TikTok yêu cầu, "
                "đợi trang sản phẩm tải xong rồi bấm lại nút Kéo + phân tích đầy đủ."
            ),
        }


def open_login_session(start_url: str = "") -> dict[str, Any]:
    return _run_on_worker(_open_login_session_internal, start_url)


def _close_session_internal() -> dict[str, Any]:
    with _lock:
        _reset_browser_state(stop_playwright=True)
    return {**_session_status_internal(), "message": "Đã đóng phiên trình duyệt TikTok Shop."}


def close_session() -> dict[str, Any]:
    if _worker_thread is None or not _worker_thread.is_alive():
        return {
            "available": True,
            "active": False,
            "profile_dir": str(_profile_dir()),
            "message": "Không có phiên trình duyệt TikTok Shop đang mở.",
        }
    return _run_on_worker(_close_session_internal)


def _fallback_review_url() -> str:
    if settings.TIKTOK_SHOP_X_TTS_OEC_BSID:
        return f"{DEFAULT_REVIEW_URL}?X-Tts-Oec-Bsid={quote(settings.TIKTOK_SHOP_X_TTS_OEC_BSID)}"
    return DEFAULT_REVIEW_URL


def _discover_review_api_url(page: Any) -> str:
    global _last_review_api_url

    for _ in range(4):
        try:
            urls = page.evaluate(
                """
                () => performance.getEntriesByType('resource')
                  .map(entry => entry.name || '')
                  .filter(name => name.includes('/api/shop/pdp_desktop/get_product_reviews'))
                """
            )
        except Exception as exc:
            if _is_closed_browser_error(exc):
                raise TikTokBrowserSessionRequired(
                    "Phiên TikTok Shop vừa bị đóng. Hãy bấm Mở phiên TikTok để backend mở lại cửa sổ rồi kéo lại."
                ) from exc
            raise
        if urls:
            _last_review_api_url = urls[urls.length - 1] if hasattr(urls, "length") else urls[-1]
            return _last_review_api_url
        try:
            page.mouse.wheel(0, 1400)
            page.wait_for_timeout(1200)
        except Exception as exc:
            if _is_closed_browser_error(exc):
                raise TikTokBrowserSessionRequired(
                    "Phiên TikTok Shop vừa bị đóng. Hãy bấm Mở phiên TikTok để backend mở lại cửa sổ rồi kéo lại."
                ) from exc
            raise

    return _last_review_api_url or _fallback_review_url()


def _fetch_review_page(page: Any, review_url: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return page.evaluate(
            """
            async ({ url, payload }) => {
              const response = await fetch(url, {
                method: 'POST',
                credentials: 'include',
                headers: {
                  'accept': 'application/json,*/*;q=0.8',
                  'content-type': 'application/json'
                },
                body: JSON.stringify(payload)
              });
              const text = await response.text();
              let body;
              try {
                body = JSON.parse(text);
              } catch (error) {
                body = { code: -1, message: text.slice(0, 300) };
              }
              body.__http_status = response.status;
              return body;
            }
            """,
            {"url": review_url, "payload": payload},
        )
    except Exception as exc:
        if _is_closed_browser_error(exc):
            raise TikTokBrowserSessionRequired(
                "Phiên TikTok Shop vừa bị đóng trong lúc kéo review. Hãy bấm Mở phiên TikTok rồi chạy lại."
            ) from exc
        raise


def fetch_reviews_with_browser(
    product_url: str,
    product_id: str,
    page_size: int = 20,
    max_pages_per_star: int = 20,
    delay: float = 1.0,
) -> list[dict[str, Any]]:
    return _run_on_worker(
        _fetch_reviews_with_browser_internal,
        product_url,
        product_id,
        page_size,
        max_pages_per_star,
        delay,
    )


def _fetch_reviews_with_browser_internal(
    product_url: str,
    product_id: str,
    page_size: int = 20,
    max_pages_per_star: int = 20,
    delay: float = 1.0,
) -> list[dict[str, Any]]:
    if not _has_active_context():
        raise TikTokBrowserSessionRequired(
            "Chưa có phiên trình duyệt TikTok Shop. Hãy bấm Mở phiên TikTok, đăng nhập nếu cần rồi chạy lại."
        )

    all_reviews: list[dict[str, Any]] = []
    page_size = max(1, min(int(page_size), 20))
    max_pages_per_star = max(1, int(max_pages_per_star))

    with _lock:
        _, page = _ensure_context(product_url)
        page.wait_for_timeout(2500)
        review_url = _discover_review_api_url(page)

        for star in [5, 4, 3, 2, 1]:
            star_count = 0
            for page_start in range(1, max_pages_per_star + 1):
                payload = {
                    "component_name": "pdp_left_reviews",
                    "page_size": page_size,
                    "page_start": page_start,
                    "product_id": str(product_id),
                    "review_filter": {"filter_type": 1, "filter_value": star},
                    "sort_rule": 1,
                }
                data = _fetch_review_page(page, review_url, payload)
                if data.get("code") not in (0, "0", None):
                    if not all_reviews and star_count == 0:
                        raise RuntimeError(f"TikTok Shop browser API error: {data}")
                    break

                reviews = ((data.get("data") or {}).get("product_reviews") or [])
                if not reviews:
                    break

                for review in reviews:
                    review["sample_type"] = f"{star}_star"
                    review["sample_filter_value"] = star
                    review["sample_page_start"] = page_start
                all_reviews.extend(reviews)
                star_count += len(reviews)

                if not (data.get("data") or {}).get("has_more"):
                    break
                time.sleep(max(delay, 0.5))

    all_reviews.sort(key=_review_timestamp, reverse=True)
    return all_reviews
