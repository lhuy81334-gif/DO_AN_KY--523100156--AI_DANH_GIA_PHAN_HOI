import argparse
import re
import shlex
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / "backend" / ".env"
DEFAULT_HEADERS_PATH = ROOT / "data" / "private" / "tiktok_shop_get_product_reviews.curl.txt"


KEY_MAP = {
    "cookie": "TIKTOK_SHOP_COOKIE",
    "user-agent": "TIKTOK_SHOP_USER_AGENT",
    "x-tts-oec-bsid": "TIKTOK_SHOP_X_TTS_OEC_BSID",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Fill TikTok Shop headers into backend/.env from Copy as cURL")
    parser.add_argument(
        "headers_file",
        nargs="?",
        default=str(DEFAULT_HEADERS_PATH),
        help=f"Text file containing Copy as cURL from the TikTok Shop review request. Default: {DEFAULT_HEADERS_PATH}",
    )
    args = parser.parse_args()

    headers_path = Path(args.headers_file)
    if not headers_path.exists():
        raise SystemExit(
            f"Chua thay file {headers_path}. Hay tao file nay va dan nguyen Copy as cURL cua request get_product_reviews vao do."
        )

    source = headers_path.read_text(encoding="utf-8")
    values = extract_headers(source)
    if "TIKTOK_SHOP_COOKIE" not in values:
        raise SystemExit("Khong tim thay Cookie. Hay dung Copy as cURL cua request get_product_reviews.")

    shortened = [key for key, value in values.items() if "..." in value or "…" in value]
    if shortened:
        raise SystemExit(f"Cac header nay dang bi rut gon bang .../…: {', '.join(shortened)}. Hay dung Copy as cURL, khong copy bang preview table.")

    env = read_env(ENV_PATH)
    env.update(values)
    write_env(ENV_PATH, env)
    print(f"Updated {ENV_PATH}")
    print("Filled:", ", ".join(sorted(values)))


def extract_headers(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    values.update(extract_curl_headers(text))
    values.update(extract_markdown_table_headers(text))

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or ":" not in line:
            continue
        name, value = line.split(":", 1)
        key = KEY_MAP.get(name.strip().lower())
        if key:
            values[key] = clean_value(value.strip())
    return values


def extract_markdown_table_headers(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith("|") or "|" not in line[1:]:
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 2:
            continue
        name = cells[0].strip()
        value = cells[1].strip()
        if not name or set(name) <= {"-"}:
            continue
        key = KEY_MAP.get(name.lower())
        if key and value and set(value) > {"-"}:
            values[key] = clean_value(value)
    return values


def extract_curl_headers(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    if not text.lstrip().lower().startswith("curl"):
        return values

    values.update(extract_curl_url_params(text))

    patterns = [
        r"(?:-H|--header)\s+\^?\"(?P<header>.*?)(?<!\\)\^?\"",
        r"(?:-H|--header)\s+'(?P<header>.*?)(?<!\\)'",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE | re.DOTALL):
            add_header(values, match.group("header"))

    for posix in (True, False):
        try:
            parts = shlex.split(text, posix=posix)
        except ValueError:
            continue
        for idx, part in enumerate(parts):
            if part not in ("-H", "--header") or idx + 1 >= len(parts):
                continue
            add_header(values, parts[idx + 1].strip().strip("'\""))
    return values


def extract_curl_url_params(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    match = re.search(r"curl(?:\.exe)?\s+\^?[\"'](?P<url>https?://[^\"']+)\^?[\"']", text, flags=re.IGNORECASE)
    if not match:
        return values
    url = clean_value(match.group("url"))
    query = parse_qs(urlparse(url).query)
    bsid = query.get("X-Tts-Oec-Bsid") or query.get("x-tts-oec-bsid")
    if bsid and bsid[0]:
        values["TIKTOK_SHOP_X_TTS_OEC_BSID"] = clean_value(bsid[0])
    return values


def add_header(values: dict[str, str], header: str) -> None:
    header = header.strip().replace("\r", "").replace("\n", "")
    if ":" not in header:
        return
    name, value = header.split(":", 1)
    key = KEY_MAP.get(name.strip().lower())
    if key:
        values[key] = clean_value(value.strip())


def clean_value(value: str) -> str:
    value = value.replace("^", "")
    value = value.replace("\\|", "|").replace("\\_", "_").replace("\\&", "&")
    return value.strip()


def read_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key] = value
    return env


def write_env(path: Path, env: dict[str, str]) -> None:
    preferred_order = [
        "PROJECT_NAME",
        "ENVIRONMENT",
        "DEBUG",
        "HOST",
        "PORT",
        "MONGODB_URL",
        "MONGODB_DATABASE",
        "LAZADA_MTOP_APP_KEY",
        "LAZADA_MTOP_URL",
        "LAZADA_MTOP_COOKIE",
        "LAZADA_MTOP_USER_AGENT",
        "LAZADA_MTOP_X_UA",
        "LAZADA_MTOP_X_UMIDTOKEN",
        "LAZADA_MTOP_TIMEOUT_SECONDS",
        "TIKI_CLIENT_ID",
        "TIKI_CLIENT_SECRET",
        "TIKTOK_SHOP_COOKIE",
        "TIKTOK_SHOP_USER_AGENT",
        "TIKTOK_SHOP_X_TTS_OEC_BSID",
        "TIKTOK_SHOP_TIMEOUT_SECONDS",
    ]
    lines: list[str] = []
    seen: set[str] = set()
    for key in preferred_order:
        if key in env:
            lines.append(f"{key}={env[key]}")
            seen.add(key)
    for key in sorted(set(env) - seen):
        lines.append(f"{key}={env[key]}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
