from __future__ import annotations

"""OpenSubtitles 网页版字幕源(opensubtitles.org)。

该站点有反爬拦截(401 bot 检测),需要自建 FlareSolverr 服务配合:
- 直接请求失败时,自动改走 FlareSolverr 的 request.get 获取页面;
- 二进制字幕下载走 FlareSolverr 的 returnOnlyBase64。

搜索页与详情页结构可能随站点改版而变化,解析采用容错方式;
如失效请检查 FlareSolverr 配置与页面结构。
"""

import base64
import html
import re
from pathlib import Path
from typing import Callable
from urllib.parse import quote

import requests

from app.models import SubtitleResult
from app.providers.base import ProviderError, SubtitleProvider
from app.providers.save import save_subtitle_bytes

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

# 搜索条目链接:/zh/subtitles/{id}(或 /en/subtitles/{id})
_SUB_LINK = re.compile(r'href="/(?:zh|en|all)/subtitles/(\d+)[^"]*"[^>]*>(.*?)</a>', re.S)
# 下载链接:优先 /download/{id},其次 dl.opensubtitles.org 直链
_DOWNLOAD = re.compile(r'href="(/download/[^"]+)"', re.I)
_DL_LINK = re.compile(r'href="(https?://dl\.opensubtitles\.org[^"]+)"', re.I)
_BOT_PAGE = re.compile(r"making sure you're not a bot|security check", re.I)


def _strip_tags(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", text)).strip()


class OpenSubtitlesWebProvider(SubtitleProvider):
    name = "opensubtitles"
    label = "OpenSubtitles 网页"
    requires_credentials = False

    def __init__(
        self,
        flaresolverr_provider: Callable[[], str],
        timeout: int = 25,
        base_url: str = "https://www.opensubtitles.org",
    ):
        self.base_url = base_url.rstrip("/")
        self.flaresolverr_provider = flaresolverr_provider
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    @property
    def configured(self) -> bool:
        return bool(self.flaresolverr_provider().strip())

    def _flaresolverr_url(self) -> str:
        url = self.flaresolverr_provider().strip().rstrip("/")
        if not url:
            raise ProviderError("OpenSubtitles 网页版需要 FlareSolverr 服务地址")
        return url

    def _direct(self, url: str) -> requests.Response:
        return self.session.get(url, timeout=self.timeout)

    def _via_flaresolverr(self, url: str, binary: bool = False) -> bytes | str:
        solver = self._flaresolverr_url()
        command: dict = {"cmd": "request.get", "url": url, "maxTimeout": 60000}
        if binary:
            command["returnOnlyBase64"] = True
        try:
            response = self.session.post(f"{solver}/v1", json=command, timeout=max(self.timeout, 90))
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise ProviderError(f"FlareSolverr 请求失败：{exc}") from exc
        solution = payload.get("solution") or {}
        status = solution.get("status") or payload.get("status")
        if status not in (200, "200"):
            message = payload.get("message") or solution.get("error") or payload
            raise ProviderError(f"FlareSolverr 返回异常：{message}")
        return solution.get("response") or ""

    def _fetch_html(self, url: str) -> str:
        try:
            response = self._direct(url)
            if response.status_code == 200 and not _BOT_PAGE.search(response.text):
                response.encoding = response.apparent_encoding or "utf-8"
                return response.text
        except requests.RequestException:
            pass
        result = self._via_flaresolverr(url, binary=False)
        return result if isinstance(result, str) else result.decode("utf-8", errors="replace")

    def search(self, keyword: str) -> list[SubtitleResult]:
        url = f"{self.base_url}/zh/search/sublanguageid-all/moviename-{quote(keyword)}"
        try:
            page = self._fetch_html(url)
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(f"OpenSubtitles 网页搜索失败：{exc}") from exc
        results: list[SubtitleResult] = []
        seen: set[str] = set()
        for match in _SUB_LINK.finditer(page):
            subtitle_id = match.group(1)
            if subtitle_id in seen:
                continue
            seen.add(subtitle_id)
            title = _strip_tags(match.group(2))
            if not title:
                continue
            results.append(SubtitleResult(
                provider=self.name,
                id=subtitle_id,
                title=title,
                movie_title=title,
                detail_url=f"{self.base_url}/zh/subtitles/{subtitle_id}",
            ))
        if not results:
            raise ProviderError("OpenSubtitles 网页搜索未解析到结果(可能页面结构变化)")
        return results

    def download(self, subtitle_id: str, detail_url: str, title: str, dest_dir: Path) -> Path:
        detail_url = detail_url or f"{self.base_url}/zh/subtitles/{subtitle_id}"
        page = self._fetch_html(detail_url)
        download_url = ""
        match = _DOWNLOAD.search(page)
        if match:
            download_url = f"{self.base_url}{match.group(1)}"
        else:
            match = _DL_LINK.search(page)
            if match:
                download_url = match.group(1)
        if not download_url:
            raise ProviderError("OpenSubtitles 详情页未找到下载链接")
        try:
            response = self._direct(download_url)
            if response.status_code != 200 or not response.content:
                data = self._via_flaresolverr(download_url, binary=True)
                raw = base64.b64decode(data) if isinstance(data, str) else data
            else:
                raw = response.content
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(f"OpenSubtitles 网页下载失败：{exc}") from exc
        return save_subtitle_bytes(raw, f"{title or subtitle_id}.srt", dest_dir)
