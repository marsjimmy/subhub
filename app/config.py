from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path


def _env_path(name: str, default: str) -> Path:
    return Path(os.getenv(name, default)).expanduser().resolve()


def _ensure_token(storage: Path, env_value: str) -> str:
    """API 令牌:优先环境变量,否则在数据目录持久化自动生成。"""
    value = env_value.strip()
    if value:
        return value
    try:
        if storage.is_file():
            token = storage.read_text(encoding="utf-8").strip()
            if token:
                return token
        token = secrets.token_urlsafe(32)
        storage.parent.mkdir(parents=True, exist_ok=True)
        storage.write_text(token, encoding="utf-8")
        try:
            storage.chmod(0o600)
        except OSError:
            pass
        return token
    except OSError:
        return secrets.token_urlsafe(32)


@dataclass(frozen=True)
class Settings:
    media_dir: Path
    data_dir: Path
    api_token: str
    request_timeout: int = int(os.getenv("REQUEST_TIMEOUT", "25"))
    max_search_pages: int = int(os.getenv("MAX_SEARCH_PAGES", "1"))
    search_cache_ttl: int = max(0, int(os.getenv("SEARCH_CACHE_TTL", "600")))
    subhd_base: str = os.getenv("SUBHD_BASE", "https://subhd.tv").strip().rstrip("/")
    zimuku_base: str = os.getenv("ZIMUKU_BASE", "https://zimuku.org").strip().rstrip("/")
    assrt_api_base: str = os.getenv("ASSRT_API_BASE", "https://api.assrt.net").strip().rstrip("/")
    opensubtitles_api_base: str = os.getenv("OPENSUBTITLES_API_BASE", "https://api.opensubtitles.com").strip().rstrip("/")


_data_dir = _env_path("DATA_DIR", "/data")
settings = Settings(
    media_dir=_env_path("MEDIA_DIR", "/media"),
    data_dir=_data_dir,
    api_token=_ensure_token(_data_dir / "api-token", os.getenv("API_TOKEN", "")),
)
