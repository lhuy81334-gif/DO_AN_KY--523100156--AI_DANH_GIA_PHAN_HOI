from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


class Settings(BaseSettings):
    PROJECT_NAME: str = "Seller Feedback Intelligence"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    PORT: int = 8000
    HOST: str = "0.0.0.0"

    MONGODB_URL: str = "mongodb://localhost:27017"
    MONGODB_DATABASE: str = "POD"

    USE_LOCAL_FALLBACK_IF_OFFLINE: bool = True

    LAZADA_MTOP_APP_KEY: str = "24677475"
    LAZADA_MTOP_URL: str = "https://acs-m.lazada.vn/h5/mtop.lazada.review.item.getpcreviewlist/1.0/"
    LAZADA_MTOP_COOKIE: str = ""
    LAZADA_MTOP_USER_AGENT: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    LAZADA_MTOP_X_UA: str = ""
    LAZADA_MTOP_X_UMIDTOKEN: str = ""
    LAZADA_MTOP_TIMEOUT_SECONDS: float = 10.0
    LAZADA_INGEST_MAX_PAGES_PER_STAR: int = 10
    LAZADA_INGEST_DELAY_SECONDS: float = 2.0
    LAZADA_INGEST_LOW_RATING_FIRST: bool = True
    LAZADA_INGEST_IMAGE_ANALYSIS_LIMIT: int = 30
    LAZADA_USE_BROWSER_SESSION: bool = True
    LAZADA_BROWSER_PROFILE_DIR: str = "data/private/lazada_browser_profile"
    LAZADA_BROWSER_HEADLESS: bool = False
    LAZADA_BROWSER_READY_WAIT_SECONDS: float = 5.0
    TIKI_CLIENT_ID: str = ""
    TIKI_CLIENT_SECRET: str = ""
    TIKTOK_SHOP_COOKIE: str = ""
    TIKTOK_SHOP_USER_AGENT: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    TIKTOK_SHOP_X_TTS_OEC_BSID: str = ""
    TIKTOK_SHOP_TIMEOUT_SECONDS: float = 10.0
    TIKTOK_SHOP_USE_BROWSER_SESSION: bool = True
    TIKTOK_SHOP_BROWSER_PROFILE_DIR: str = "data/private/tiktok_shop_browser_profile"
    TIKTOK_SHOP_BROWSER_HEADLESS: bool = False
    TIKTOK_SHOP_INGEST_MAX_PAGES_PER_STAR: int = 5
    TIKTOK_SHOP_INGEST_DELAY_SECONDS: float = 0.5
    TIKTOK_SHOP_INGEST_IMAGE_ANALYSIS_LIMIT: int = 30

    DEFAULT_BATCH_SIZE: int = 1000
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
