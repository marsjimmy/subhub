from __future__ import annotations

"""assrt(射手网(伪))开放 API 字幕源。需要注册后获取个人 token。"""

from pathlib import Path
from typing import Callable
from urllib.parse import urlencode

import requests

from app.models import SubtitleResult
from app.providers.base import ProviderError, SubtitleProvider
from app.providers.save import save_subtitle_bytes

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"


class AssrtProvider(SubtitleProvider):
    name = "assrt"
    label = "assrt"
    requires_credentials = True

    def __init__(self, api_base: str, token_provider: Callable[[], str], timeout: int = 25):
        self.api_base = api_base.rstrip("/")
        self.token_provider = token_provider
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    @property
    def configured(self) -> bool:
        return bool(self.token_provider().strip())

    def _api(self, path: str, params: dict[str, str]) -> dict:
        token = self.token_provider().strip()
        if not token:
            raise ProviderError("assrt 未配置 token")
        params = dict(params)
        params["token"] = token
        url = f"{self.api_base}{path}?{urlencode(params)}"
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise ProviderError(f"assrt 请求失败：{exc}") from exc
        if str(payload.get("status")) not in {"0", "200", "1"}:
            raise ProviderError(f"assrt 返回错误：{payload.get('errmsg', payload)}")
        return payload

    def search(self, keyword: str) -> list[SubtitleResult]:
        payload = self._api("/v1/sub/search", {"q": keyword})
        data = payload.get("data") or {}
        items = data.get("search") or []
        results: list[SubtitleResult] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            subtitle_id = str(item.get("id") or "")
            if not subtitle_id:
                continue
            filename = str(item.get("filename") or "")
            title = filename or str(item.get("subname") or keyword)
            results.append(SubtitleResult(
                provider=self.name,
                id=subtitle_id,
                title=title,
                movie_title=str(item.get("subname") or title),
                format=str(item.get("format") or ""),
                detail_url=str(item.get("url") or ""),
            ))
        return results

    def download(self, subtitle_id: str, detail_url: str, title: str, dest_dir: Path) -> Path:
        if not detail_url:
            raise ProviderError("assrt 结果缺少下载地址")
        try:
            response = self.session.get(detail_url, timeout=self.timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise ProviderError(f"assrt 下载失败：{exc}") from exc
        suggested = f"{title or subtitle_id}.srt"
        return save_subtitle_bytes(response.content, suggested, dest_dir)
