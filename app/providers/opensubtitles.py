from __future__ import annotations

"""OpenSubtitles 官方开放 API 字幕源(api.opensubtitles.com)。

按官方公开 API 实现:login → search → download。
需要注册后获取 API Key,并配置用户名与密码。
"""

from pathlib import Path
from typing import Callable

import requests

from app.models import SubtitleResult
from app.providers.base import ProviderError, SubtitleProvider
from app.providers.save import save_subtitle_bytes

USER_AGENT = "SubHub/0.1 (https://github.com/your/subhub)"


class OpenSubtitlesProvider(SubtitleProvider):
    name = "opensubtitles"
    label = "OpenSubtitles"
    requires_credentials = True

    def __init__(
        self,
        api_base: str,
        credentials_provider: Callable[[], dict[str, str]],
        timeout: int = 25,
    ):
        self.api_base = api_base.rstrip("/")
        self.credentials_provider = credentials_provider
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self._token: str | None = None

    @property
    def configured(self) -> bool:
        creds = self.credentials_provider()
        return all(creds.get(k) for k in ("api_key", "username", "password"))

    def reset_session(self) -> None:
        self._token = None

    def _login(self) -> str:
        if self._token:
            return self._token
        creds = self.credentials_provider()
        if not all(creds.get(k) for k in ("api_key", "username", "password")):
            raise ProviderError("OpenSubtitles 凭据未完整配置")
        try:
            response = self.session.post(
                f"{self.api_base}/api/v1/login",
                json={
                    "username": creds["username"],
                    "password": creds["password"],
                    "api_key": creds["api_key"],
                },
                headers={"Api-Key": creds["api_key"]},
                timeout=self.timeout,
            )
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise ProviderError(f"OpenSubtitles 登录失败：{exc}") from exc
        if response.status_code != 200:
            message = payload.get("message") or payload.get("error") or response.text
            raise ProviderError(f"OpenSubtitles 登录被拒：{message}")
        token = payload.get("token") or ""
        if not token:
            raise ProviderError("OpenSubtitles 登录响应缺少 token")
        self._token = token
        return token

    def search(self, keyword: str) -> list[SubtitleResult]:
        token = self._login()
        creds = self.credentials_provider()
        headers = {
            "Api-Key": creds["api_key"],
            "Authorization": f"Bearer {token}",
        }
        try:
            response = self.session.get(
                f"{self.api_base}/api/v1/subtitles",
                params={"query": keyword, "languages": "zh,en"},
                headers=headers,
                timeout=self.timeout,
            )
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise ProviderError(f"OpenSubtitles 搜索失败：{exc}") from exc
        if response.status_code != 200:
            message = payload.get("message") or payload.get("error") or response.text
            raise ProviderError(f"OpenSubtitles 搜索被拒：{message}")
        results: list[SubtitleResult] = []
        for item in payload.get("data") or []:
            attributes = item.get("attributes") or {}
            files = attributes.get("files") or []
            file_id = ""
            file_name = ""
            if files:
                file_id = str(files[0].get("file_id") or "")
                file_name = str(files[0].get("file_name") or "")
            subtitle_id = str(item.get("id") or file_id)
            if not subtitle_id:
                continue
            results.append(SubtitleResult(
                provider=self.name,
                id=subtitle_id,
                title=str(attributes.get("title") or file_name or keyword),
                movie_title=str(attributes.get("movie_name") or ""),
                format=str(attributes.get("format") or ""),
                detail_url=str(attributes.get("url") or ""),
            ))
        return results

    def download(self, subtitle_id: str, detail_url: str, title: str, dest_dir: Path) -> Path:
        token = self._login()
        creds = self.credentials_provider()
        headers = {
            "Api-Key": creds["api_key"],
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        try:
            response = self.session.post(
                f"{self.api_base}/api/v1/download",
                json={"file_id": int(subtitle_id) if subtitle_id.isdigit() else subtitle_id},
                headers=headers,
                timeout=self.timeout,
            )
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise ProviderError(f"OpenSubtitles 准备下载失败：{exc}") from exc
        if response.status_code != 200:
            message = payload.get("message") or payload.get("error") or response.text
            raise ProviderError(f"OpenSubtitles 下载被拒：{message}")
        link = payload.get("link") or ""
        if not link:
            raise ProviderError("OpenSubtitles 下载响应缺少链接")
        try:
            file_response = self.session.get(
                link,
                headers={"Api-Key": creds["api_key"], "User-Agent": USER_AGENT},
                timeout=self.timeout,
            )
            file_response.raise_for_status()
        except requests.RequestException as exc:
            raise ProviderError(f"OpenSubtitles 下载文件失败：{exc}") from exc
        suggested = f"{title or subtitle_id}.srt"
        return save_subtitle_bytes(file_response.content, suggested, dest_dir)
