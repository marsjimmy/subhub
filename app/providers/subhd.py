from __future__ import annotations

"""SubHD 字幕源:网页搜索(免登录) + 预览接口下载全文(免登录)。"""

import html
import re
from pathlib import Path
from urllib.parse import quote

import requests

from app.models import SubtitleResult
from app.providers.base import ProviderError, SubtitleProvider
from app.providers.save import save_subtitle_bytes

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

# 结果条目块:每个字幕条目是一个独立 div
_ENTRY = re.compile(
    r'<div class="bg-white shadow-sm rounded-3 mb-4">(.*?)</div>\s*</div>\s*</div>',
    re.S,
)
_LINK = re.compile(r"<a[^>]+href=['\"]/a/([A-Za-z0-9]+)['\"][^>]*>(.*?)</a>", re.S)
_TAG = re.compile(r"<span[^>]*class=\"p-1[^\"]*\"[^>]*>(.*?)</span>", re.S)


def _strip_tags(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", text)).strip()


class SubhdProvider(SubtitleProvider):
    name = "subhd"
    label = "SubHD"
    requires_credentials = False

    def __init__(self, base_url: str, timeout: int = 25):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    def _get(self, url: str, *, referer: str = "") -> requests.Response:
        headers = {}
        if referer:
            headers["Referer"] = referer
        try:
            response = self.session.get(url, headers=headers, timeout=self.timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise ProviderError(f"SubHD 请求失败：{exc}") from exc
        return response

    def search(self, keyword: str) -> list[SubtitleResult]:
        url = f"{self.base_url}/search/{quote(keyword)}"
        response = self._get(url)
        response.encoding = response.apparent_encoding or "utf-8"
        raw = response.text
        results: list[SubtitleResult] = []
        seen: set[str] = set()
        for block in _ENTRY.finditer(raw):
            block_html = block.group(1)
            links = _LINK.findall(block_html)
            if not links:
                continue
            sid = links[0][0]
            if sid in seen:
                continue
            seen.add(sid)
            title = _strip_tags(links[0][1]) or keyword
            version = _strip_tags(links[1][1]) if len(links) > 1 else ""
            formats = " / ".join(dict.fromkeys(
                _strip_tags(t) for t in _TAG.findall(block_html) if _strip_tags(t)
            ))
            results.append(SubtitleResult(
                provider=self.name,
                id=sid,
                title=title,
                movie_title=version or title,
                format=formats,
                detail_url=f"{self.base_url}/a/{sid}",
            ))
        return results

    def download(self, subtitle_id: str, detail_url: str, title: str, dest_dir: Path) -> Path:
        preview_url = f"{self.base_url}/api/sub/preview/{subtitle_id}"
        try:
            response = self._get(preview_url, referer=f"{self.base_url}/a/{subtitle_id}")
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise ProviderError(f"SubHD 获取字幕失败：{exc}") from exc
        if not payload.get("success"):
            raise ProviderError(f"SubHD 返回失败：{payload.get('message', payload)}")
        file_info = payload.get("file") or {}
        content = file_info.get("content") or ""
        if not content:
            raise ProviderError("SubHD 字幕内容为空")
        filename = file_info.get("filename") or f"{title}.srt"
        data = content.encode("utf-8")
        return save_subtitle_bytes(data, filename, dest_dir)
