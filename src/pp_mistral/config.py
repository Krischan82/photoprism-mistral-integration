import os
from dataclasses import dataclass


def _bool(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _int(name: str, default: int) -> int:
    val = os.environ.get(name)
    return int(val) if val else default


def _require(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return val


@dataclass
class Settings:
    photoprism_url: str
    photoprism_client_id: str | None
    photoprism_client_secret: str | None
    photoprism_username: str | None
    photoprism_password: str | None

    mistral_api_key: str
    mistral_model: str

    enable_description: bool
    enable_keywords: bool
    enable_geolocation: bool
    overwrite_existing: bool

    batch_size: int
    max_photos_per_run: int
    sync_interval_seconds: int
    dry_run: bool

    geocode_user_agent: str

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            photoprism_url=_require("PHOTOPRISM_URL"),
            photoprism_client_id=os.environ.get("PHOTOPRISM_CLIENT_ID"),
            photoprism_client_secret=os.environ.get("PHOTOPRISM_CLIENT_SECRET"),
            photoprism_username=os.environ.get("PHOTOPRISM_USERNAME"),
            photoprism_password=os.environ.get("PHOTOPRISM_PASSWORD"),
            mistral_api_key=_require("MISTRAL_API_KEY"),
            mistral_model=os.environ.get("MISTRAL_MODEL", "pixtral-large-latest"),
            enable_description=_bool("ENABLE_DESCRIPTION", True),
            enable_keywords=_bool("ENABLE_KEYWORDS", True),
            enable_geolocation=_bool("ENABLE_GEOLOCATION", True),
            overwrite_existing=_bool("OVERWRITE_EXISTING", False),
            batch_size=_int("BATCH_SIZE", 100),
            max_photos_per_run=_int("MAX_PHOTOS_PER_RUN", 0),
            sync_interval_seconds=_int("SYNC_INTERVAL_SECONDS", 3600),
            dry_run=_bool("DRY_RUN", False),
            geocode_user_agent=os.environ.get(
                "GEOCODE_USER_AGENT", "photoprism-mistral-integration/1.0"
            ),
        )
