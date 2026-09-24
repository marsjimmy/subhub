from __future__ import annotations

import asyncio
import secrets
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.openapi.utils import get_openapi
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.models import (
    AssrtSettingsStatus,
    AssrtSettingsUpdate,
    CacheClearResponse,
    DatabaseStats,
    DownloadHistoryItem,
    DownloadRequest,
    DownloadResponse,
    FlareSolverrSettings,
    MediaFile,
    OpenSubtitlesSettingsStatus,
    OpenSubtitlesSettingsUpdate,
    PatternTestRequest,
    PatternTestResponse,
    ProviderSettings,
    SearchHistoryItem,
    SearchResponse,
    SubtitleResult,
    TitlePatterns,
)
from app.providers import (
    AssrtProvider,
    OpenSubtitlesProvider,
    OpenSubtitlesWebProvider,
    ProviderError,
    SubhdProvider,
    SubtitleProvider,
    ZimukuProvider,
)
from app.services.media_library import (
    MediaLibrary,
    place_subtitle_for_strm,
    clean_title,
)
from app.services.store import Store, validate_patterns
from app.version import APP_NAME, APP_SLUG, APP_VERSION

app = FastAPI(title=f"{APP_NAME} ({APP_SLUG})", version=APP_VERSION)
store = Store(settings.data_dir / "subhub.db")

library = MediaLibrary(settings.media_dir, store.get_title_patterns, store)

providers: dict[str, SubtitleProvider] = {
    "zimuku": ZimukuProvider(settings.zimuku_base, settings.request_timeout),
    "subhd": SubhdProvider(settings.subhd_base, settings.request_timeout),
    "assrt": AssrtProvider(settings.assrt_api_base, lambda: store.get_setting("assrt_token"), settings.request_timeout),
    "opensubtitles": OpenSubtitlesWebProvider(
        lambda: store.get_setting("flaresolverr_url"), settings.request_timeout
    ),
    "opensubtitles_api": OpenSubtitlesProvider(
        settings.opensubtitles_api_base,
        lambda: {
            "api_key": store.get_setting("os_api_key"),
            "username": store.get_setting("os_username"),
            "password": store.get_setting("os_password"),
        },
        settings.request_timeout,
    ),
}


@app.middleware("http")
async def authenticate_api(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/") and path != "/api/health":
        scheme, _, token = request.headers.get("Authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not secrets.compare_digest(token, settings.api_token):
            return JSONResponse(
                status_code=401,
                content={"detail": "访问令牌无效或已失效"},
                headers={"WWW-Authenticate": "Bearer"},
            )
    return await call_next(request)


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
    schema.setdefault("components", {}).setdefault("securitySchemes", {})["BearerAuth"] = {
        "type": "http",
        "scheme": "bearer",
    }
    for path, methods in schema.get("paths", {}).items():
        if path == "/api/health":
            continue
        for operation in methods.values():
            if isinstance(operation, dict):
                operation["security"] = [{"BearerAuth": []}]
    app.openapi_schema = schema
    return schema


app.openapi = custom_openapi


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/web-api/config", include_in_schema=False)
@app.get("/api/config")
def public_config() -> dict[str, object]:
    return {
        "name": APP_NAME,
        "slug": APP_SLUG,
        "version": APP_VERSION,
        "media_dir": str(settings.media_dir),
        "data_dir": str(settings.data_dir),
        "providers": list(providers),
    }


@app.get("/web-api/media", response_model=list[MediaFile], include_in_schema=False)
@app.get("/api/media", response_model=list[MediaFile])
def scan_media() -> list[MediaFile]:
    try:
        return library.scan()
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"扫描媒体库失败：{exc}") from exc


@app.get("/web-api/media/{media_id}/poster", include_in_schema=False)
@app.get("/api/media/{media_id}/poster", include_in_schema=False)
def media_poster(media_id: str):
    try:
        return FileResponse(library.poster_path(media_id))
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/web-api/settings/title-patterns", response_model=TitlePatterns, include_in_schema=False)
@app.get("/api/settings/title-patterns", response_model=TitlePatterns)
def get_title_patterns() -> TitlePatterns:
    return TitlePatterns(patterns=store.get_title_patterns())


@app.put("/web-api/settings/title-patterns", response_model=TitlePatterns, include_in_schema=False)
@app.put("/api/settings/title-patterns", response_model=TitlePatterns)
def save_title_patterns(request: TitlePatterns) -> TitlePatterns:
    try:
        return TitlePatterns(patterns=store.save_title_patterns(request.patterns))
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/web-api/settings/title-patterns/test", response_model=PatternTestResponse, include_in_schema=False)
@app.post("/api/settings/title-patterns/test", response_model=PatternTestResponse)
def test_title_patterns(request: PatternTestRequest) -> PatternTestResponse:
    try:
        patterns = validate_patterns(request.patterns)
        return PatternTestResponse(title=clean_title(request.filename, patterns))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/web-api/settings/providers", response_model=ProviderSettings, include_in_schema=False)
@app.get("/api/settings/providers", response_model=ProviderSettings)
def get_provider_settings() -> ProviderSettings:
    return ProviderSettings(providers=store.get_provider_states())


@app.put("/web-api/settings/providers", response_model=ProviderSettings, include_in_schema=False)
@app.put("/api/settings/providers", response_model=ProviderSettings)
def save_provider_settings(request: ProviderSettings) -> ProviderSettings:
    try:
        return ProviderSettings(providers=store.save_provider_states(request.providers))
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/web-api/settings/assrt", response_model=AssrtSettingsStatus, include_in_schema=False)
@app.get("/api/settings/assrt", response_model=AssrtSettingsStatus)
def get_assrt_settings() -> AssrtSettingsStatus:
    token = store.get_setting("assrt_token")
    return AssrtSettingsStatus(configured=bool(token), token_set=bool(token))


@app.put("/web-api/settings/assrt", response_model=AssrtSettingsStatus, include_in_schema=False)
@app.put("/api/settings/assrt", response_model=AssrtSettingsStatus)
def save_assrt_settings(request: AssrtSettingsUpdate) -> AssrtSettingsStatus:
    token = (request.token or "").strip()
    if not token:
        store.clear_setting("assrt_token")
        store.save_provider_states({"assrt": False})
    else:
        store.save_setting("assrt_token", token)
        store.save_provider_states({"assrt": True})
    store.clear_search_cache("assrt")
    return AssrtSettingsStatus(configured=bool(token), token_set=bool(token))


@app.get("/web-api/settings/opensubtitles", response_model=FlareSolverrSettings, include_in_schema=False)
@app.get("/api/settings/opensubtitles", response_model=FlareSolverrSettings)
def get_opensubtitles_settings() -> FlareSolverrSettings:
    return FlareSolverrSettings(url=store.get_setting("flaresolverr_url"))


@app.put("/web-api/settings/opensubtitles", response_model=FlareSolverrSettings, include_in_schema=False)
@app.put("/api/settings/opensubtitles", response_model=FlareSolverrSettings)
def save_opensubtitles_settings(request: FlareSolverrSettings) -> FlareSolverrSettings:
    url = (request.url or "").strip()
    if not url:
        store.clear_setting("flaresolverr_url")
        store.save_provider_states({"opensubtitles": False})
    else:
        store.save_setting("flaresolverr_url", url)
        store.save_provider_states({"opensubtitles": True})
    store.clear_search_cache("opensubtitles")
    return FlareSolverrSettings(url=url)


@app.get("/web-api/settings/opensubtitles-api", response_model=OpenSubtitlesSettingsStatus, include_in_schema=False)
@app.get("/api/settings/opensubtitles-api", response_model=OpenSubtitlesSettingsStatus)
def get_opensubtitles_api_settings() -> OpenSubtitlesSettingsStatus:
    values = {
        "api_key": store.get_setting("os_api_key"),
        "username": store.get_setting("os_username"),
        "password": store.get_setting("os_password"),
    }
    return OpenSubtitlesSettingsStatus(
        configured=all(values.values()),
        api_key_set=bool(values["api_key"]),
        username_set=bool(values["username"]),
        password_set=bool(values["password"]),
    )


@app.put("/web-api/settings/opensubtitles-api", response_model=OpenSubtitlesSettingsStatus, include_in_schema=False)
@app.put("/api/settings/opensubtitles-api", response_model=OpenSubtitlesSettingsStatus)
def save_opensubtitles_api_settings(request: OpenSubtitlesSettingsUpdate) -> OpenSubtitlesSettingsStatus:
    current = {
        "api_key": store.get_setting("os_api_key"),
        "username": store.get_setting("os_username"),
        "password": store.get_setting("os_password"),
    }
    merged = {
        "api_key": (request.api_key or "").strip() or current["api_key"],
        "username": (request.username or "").strip() or current["username"],
        "password": request.password if request.password else current["password"],
    }
    if not all(merged.values()):
        raise HTTPException(status_code=422, detail="API Key、用户名和密码必须全部填写")
    for key, value in merged.items():
        store.save_setting(f"os_{key}", value)
    store.save_provider_states({"opensubtitles_api": True})
    providers["opensubtitles_api"].reset_session()
    store.clear_search_cache("opensubtitles_api")
    return OpenSubtitlesSettingsStatus(
        configured=True,
        api_key_set=True,
        username_set=True,
        password_set=True,
    )


@app.delete("/web-api/settings/opensubtitles-api", response_model=OpenSubtitlesSettingsStatus, include_in_schema=False)
@app.delete("/api/settings/opensubtitles-api", response_model=OpenSubtitlesSettingsStatus)
def clear_opensubtitles_api_settings() -> OpenSubtitlesSettingsStatus:
    for key in ("os_api_key", "os_username", "os_password"):
        store.clear_setting(key)
    store.save_provider_states({"opensubtitles_api": False})
    providers["opensubtitles_api"].reset_session()
    store.clear_search_cache("opensubtitles_api")
    return OpenSubtitlesSettingsStatus(configured=False, api_key_set=False, username_set=False, password_set=False)


async def _search_one(provider: SubtitleProvider, keyword: str, refresh: bool):
    if not refresh and settings.search_cache_ttl:
        cached = store.get_search_cache(keyword, provider.name)
        if cached is not None:
            return provider.name, [SubtitleResult(**item) for item in cached], None, True
    try:
        items = await run_in_threadpool(provider.search, keyword)
        if settings.search_cache_ttl:
            store.save_search_cache(
                keyword,
                provider.name,
                [item.model_dump() for item in items],
                settings.search_cache_ttl,
            )
        return provider.name, items, None, False
    except Exception as exc:
        return provider.name, [], str(exc), False


@app.get("/web-api/search", response_model=SearchResponse, include_in_schema=False)
@app.get("/api/search", response_model=SearchResponse)
async def search_subtitles(
    media_id: str | None = None,
    keyword: str | None = None,
    source: list[str] | None = Query(default=None),
    refresh: bool = False,
) -> SearchResponse:
    if media_id:
        try:
            keyword = library.get(media_id).title
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    keyword = (keyword or "").strip()
    if not keyword:
        raise HTTPException(status_code=422, detail="media_id 或 keyword 至少填写一个")

    provider_states = store.get_provider_states()
    enabled_names = {name for name, enabled in provider_states.items() if enabled}
    selected_names = source or [
        name for name, provider in providers.items()
        if name in enabled_names and provider.configured
    ]
    selected_names = list(dict.fromkeys(selected_names))
    unknown = sorted(set(selected_names) - set(providers))
    if unknown:
        raise HTTPException(status_code=422, detail=f"未知字幕源：{', '.join(unknown)}")
    disabled = sorted(set(selected_names) - enabled_names)
    if disabled:
        raise HTTPException(status_code=422, detail=f"字幕源未开启：{', '.join(disabled)}")

    selected = [providers[name] for name in selected_names]
    searches = await asyncio.gather(*(_search_one(provider, keyword, refresh) for provider in selected))
    results: list[SubtitleResult] = []
    errors: dict[str, str] = {}
    cached_sources: list[str] = []
    for name, items, error, cache_hit in searches:
        results.extend(items)
        if error:
            errors[name] = error
        if cache_hit:
            cached_sources.append(name)
    store.record_search(keyword, selected_names, len(cached_sources), len(results), len(errors))
    return SearchResponse(keyword=keyword, results=results, errors=errors, cached_sources=cached_sources)


@app.post("/web-api/download", response_model=DownloadResponse, include_in_schema=False)
@app.post("/api/download", response_model=DownloadResponse)
async def download_subtitle(request: DownloadRequest) -> DownloadResponse:
    provider = providers.get(request.provider)
    if provider is None:
        raise HTTPException(status_code=422, detail="未知字幕源")
    if not store.get_provider_states().get(request.provider, False):
        raise HTTPException(status_code=422, detail="字幕源未开启")
    history_id = store.start_download(request.provider, request.subtitle_id, request.title)
    saved_dir = "downloads"
    note = ""
    try:
        path = await run_in_threadpool(
            provider.download,
            request.subtitle_id,
            request.detail_url,
            request.title,
            settings.data_dir / "downloads",
        )
        saved = path
        relative_path = str(path.relative_to(settings.data_dir / "downloads"))
        if request.media_id:
            try:
                media = library.get(request.media_id)
            except (ValueError, FileNotFoundError):
                media = None
            if media is not None and media.is_strm:
                try:
                    saved, relative_path = place_subtitle_for_strm(
                        settings.media_dir,
                        media.path,
                        path,
                    )
                    saved_dir = "media"
                except OSError as exc:
                    note = f"媒体目录不可写（{exc}），字幕已保存到字幕目录"
        store.finish_download(history_id, saved.name, relative_path)
    except Exception as exc:
        store.fail_download(history_id, str(exc))
        raise HTTPException(status_code=502, detail=f"下载失败：{exc}") from exc
    return DownloadResponse(
        history_id=history_id,
        filename=saved.name,
        path=relative_path,
        provider=provider.name,
        note=note,
        saved_dir=saved_dir,
    )


@app.get("/api/history/downloads", response_model=list[DownloadHistoryItem])
def download_history(limit: int = Query(default=100, ge=1, le=500)) -> list[DownloadHistoryItem]:
    return [DownloadHistoryItem(**item) for item in store.list_download_history(limit)]


@app.get("/api/history/searches", response_model=list[SearchHistoryItem])
def search_history(limit: int = Query(default=100, ge=1, le=500)) -> list[SearchHistoryItem]:
    return [SearchHistoryItem(**item) for item in store.list_search_history(limit)]


@app.delete("/api/cache/search", response_model=CacheClearResponse)
def clear_search_cache(provider: str | None = None) -> CacheClearResponse:
    if provider is not None and provider not in providers:
        raise HTTPException(status_code=422, detail="未知字幕源")
    return CacheClearResponse(removed=store.clear_search_cache(provider))


@app.get("/api/database/stats", response_model=DatabaseStats)
def database_stats() -> DatabaseStats:
    return DatabaseStats(**store.database_stats())


static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(static_dir / "index.html")
