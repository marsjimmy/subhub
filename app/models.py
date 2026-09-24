from __future__ import annotations

from pydantic import BaseModel, Field


class MediaFile(BaseModel):
    id: str
    path: str
    title: str
    filename: str
    poster_url: str | None = None
    is_strm: bool = False


class TitlePatterns(BaseModel):
    patterns: list[str]


class PatternTestRequest(BaseModel):
    filename: str
    patterns: list[str]


class PatternTestResponse(BaseModel):
    title: str


class ProviderSettings(BaseModel):
    providers: dict[str, bool]


class FlareSolverrSettings(BaseModel):
    url: str


class SubtitleResult(BaseModel):
    provider: str
    id: str
    title: str
    movie_title: str = ""
    format: str = ""
    detail_url: str = ""


class SearchResponse(BaseModel):
    keyword: str
    results: list[SubtitleResult]
    errors: dict[str, str] = Field(default_factory=dict)
    cached_sources: list[str] = Field(default_factory=list)


class DownloadRequest(BaseModel):
    provider: str
    subtitle_id: str
    detail_url: str = ""
    title: str
    media_id: str | None = None


class DownloadResponse(BaseModel):
    history_id: int
    filename: str
    path: str
    provider: str
    note: str = ""
    saved_dir: str = "downloads"


class CredentialStatus(BaseModel):
    subhd: bool = True
    assrt: bool = False
    opensubtitles: bool = False


class AssrtSettingsUpdate(BaseModel):
    token: str | None = None


class AssrtSettingsStatus(BaseModel):
    configured: bool
    token_set: bool


class OpenSubtitlesSettingsUpdate(BaseModel):
    api_key: str | None = None
    username: str | None = None
    password: str | None = None


class OpenSubtitlesSettingsStatus(BaseModel):
    configured: bool
    api_key_set: bool
    username_set: bool
    password_set: bool


class DownloadHistoryItem(BaseModel):
    id: int
    provider: str
    subtitle_id: str
    title: str
    filename: str
    path: str
    status: str
    error: str
    created_at: str
    completed_at: str | None = None


class SearchHistoryItem(BaseModel):
    id: int
    keyword: str
    providers: list[str]
    provider_count: int
    cache_hits: int
    result_count: int
    error_count: int
    created_at: str


class CacheClearResponse(BaseModel):
    removed: int


class DatabaseStats(BaseModel):
    download_history: int
    search_history: int
    search_cache: int
    media_index: int
