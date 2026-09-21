import argparse
import shlex
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / "backend" / ".env"


KEY_MAP = {
    "cookie": "LAZADA_MTOP_COOKIE",
    "user-agent": "LAZADA_MTOP_USER_AGENT",
    "x-ua": "LAZADA_MTOP_X_UA",
    "x-umidtoken": "LAZADA_MTOP_X_UMIDTOKEN",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Fill Lazada MTOP headers into backend/.env from copied browser request headers or Copy as cURL")
    parser.add_argument("headers_file", help="Text file containing copied Request Headers or Copy as cURL from browser Network tab")
    args = parser.parse_args()

    source = Path(args.headers_file).read_text(encoding="utf-8")
    values = extract_headers(source)
    if "LAZADA_MTOP_COOKIE" not in values:
        raise SystemExit("Could not find a Cookie header. Use Copy as cURL from the Network request and paste it into the file.")
    shortened = [key for key, value in values.items() if "..." in value or "…" in value]
    if shortened:
        raise SystemExit(f"These headers are shortened with .../…: {', '.join(shortened)}. Use Copy as cURL, not the preview table.")

    env = read_env(ENV_PATH)
    env.update(values)
    write_env(ENV_PATH, env)
    print(f"Updated {ENV_PATH}")
    print("Filled:", ", ".join(sorted(values)))


def extract_headers(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    values.update(extract_curl_headers(text))
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or ":" not in line:
            continue
        name, value = line.split(":", 1)
        key = KEY_MAP.get(name.strip().lower())
        if key:
            values[key] = clean_value(value.strip())
    return values


def extract_curl_headers(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    if not text.lstrip().lower().startswith("curl"):
        return values
    for match in re.finditer(r'(?:-H|--header)\s+\^?"(?P<header>.*?)\^?"', text, flags=re.IGNORECASE):
        header = match.group("header")
        if ":" not in header:
            continue
        name, value = header.split(":", 1)
        key = KEY_MAP.get(name.strip().lower())
        if key:
            values[key] = clean_value(value.strip())
    try:
        parts = shlex.split(text, posix=False)
    except ValueError:
        return values
    for idx, part in enumerate(parts):
        if part not in ("-H", "--header") or idx + 1 >= len(parts):
            continue
        header = parts[idx + 1].strip().strip("'\"")
        if ":" not in header:
            continue
        name, value = header.split(":", 1)
        key = KEY_MAP.get(name.strip().lower())
        if key:
            values[key] = clean_value(value.strip())
    return values


def clean_value(value: str) -> str:
    value = re.sub(r"^\s+", "", value)
    value = value.replace("^", "")
    value = value.replace("\\|", "|").replace("\\_", "_")
    return value


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
    ]
    lines = []
    seen = set()
    for key in preferred_order:
        if key in env:
            lines.append(f"{key}={env[key]}")
            seen.add(key)
    for key in sorted(set(env) - seen):
        lines.append(f"{key}={env[key]}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
