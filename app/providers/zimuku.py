from __future__ import annotations

"""字幕库(zimuku)字幕源。

访问流程:
1. 站点有云锁验证码墙,首次访问任意页面会返回内嵌 BMP 验证码 + 会话 cookie;
2. 用 ddddocr 识别验证码后,携带 security_verify_img 参数重试同一 URL 完成放行;
3. 搜索 /search?q=... 返回影片页与字幕详情页链接;
4. 下载:详情页 → /dld/{id}.html 提取线路链接 → 下载 7z/zip 压缩包 → 解压字幕。

验证码识别失败或站点反爬变化时如实报错,不做其他绕过手段。
"""

import base64
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

_CAPTCHA_IMG = re.compile(r'data:image/bmp;base64,([A-Za-z0-9+/=]+)')
_DETAIL_LINK = re.compile(r'href="([^"]*?/detail/(\d+)\.html)"[^>]*>(.*?)</a>', re.S)
_DLD_LINK = re.compile(r'href="[^"]*?(/dld/(\d+)\.html)"', re.I)
_DOWNLOAD_LINK = re.compile(r'href="(/download/[^"]+)"')


def _strip_tags(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", text)).strip()


def _absolute(href: str, base_url: str) -> str:
    if href.startswith("//"):
        return "https:" + href
    if href.startswith("/"):
        return base_url + href
    return href


class ZimukuProvider(SubtitleProvider):
    name = "zimuku"
    label = "字幕库"
    requires_credentials = False

    def __init__(self, base_url: str, timeout: int = 25):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self._ocr = None

    def _get_ocr(self):
        if self._ocr is None:
            try:
                import ddddocr
            except ImportError as exc:
                raise ProviderError("zimuku 需要验证码识别,但未安装 ddddocr") from exc
            self._ocr = ddddocr.DdddOcr(show_ad=False)
        return self._ocr

    def _solve_captcha(self, image_bytes: bytes) -> str:
        try:
            return self._get_ocr().classification(image_bytes)
        except Exception as exc:
            raise ProviderError(f"zimuku 验证码识别失败：{exc}") from exc

    def _fetch(self, url: str, params: dict | None = None) -> requests.Response:
        """请求 URL;若命中验证码墙,识别后带 security_verify_img 重试一次。"""
        response = self.session.get(url, params=params, timeout=self.timeout)
        match = _CAPTCHA_IMG.search(response.text)
        if match:
            text = self._solve_captcha(base64.b64decode(match.group(1)))
            hex_text = "".join(f"{ord(ch):x}" for ch in text)
            extra = dict(params or {})
            extra["security_verify_img"] = hex_text
            response = self.session.get(url, params=extra, timeout=self.timeout)
            if _CAPTCHA_IMG.search(response.text):
                raise ProviderError("zimuku 验证码放行失败,请稍后重试")
        return response

    def _bootstrap(self) -> None:
        """建立已验证会话(验证码放行首页)。"""
        try:
            self._fetch(f"{self.base_url}/")
        except requests.RequestException as exc:
            raise ProviderError(f"zimuku 请求失败：{exc}") from exc

    def search(self, keyword: str) -> list[SubtitleResult]:
        self._bootstrap()
        url = f"{self.base_url}/search"
        params = {"q": keyword, "chost": "zimuku.org"}
        try:
            response = self._fetch(url, params=params)
        except requests.RequestException as exc:
            raise ProviderError(f"zimuku 搜索失败：{exc}") from exc
        results: list[SubtitleResult] = []
        seen: set[str] = set()
        for match in _DETAIL_LINK.finditer(response.text):
            detail_id = match.group(2)
            if detail_id in seen:
                continue
            seen.add(detail_id)
            title = _strip_tags(match.group(3))
            if not title:
                continue
            results.append(SubtitleResult(
                provider=self.name,
                id=detail_id,
                title=title,
                movie_title=title,
                detail_url=_absolute(match.group(1), self.base_url),
            ))
        return results

    def download(self, subtitle_id: str, detail_url: str, title: str, dest_dir: Path) -> Path:
        detail_url = detail_url or f"{self.base_url}/detail/{subtitle_id}.html"
        try:
            detail = self._fetch(detail_url)
            dld_match = _DLD_LINK.search(detail.text)
            if not dld_match:
                raise ProviderError("zimuku 详情页未找到下载入口")
            dld_url = _absolute(dld_match.group(1), self.base_url)
            dld = self._fetch(dld_url)
            download_match = _DOWNLOAD_LINK.search(dld.text)
            if not download_match:
                raise ProviderError("zimuku 下载页未找到下载线路")
            file_response = self.session.get(
                f"{self.base_url}{download_match.group(1)}", timeout=max(self.timeout, 60)
            )
            file_response.raise_for_status()
        except requests.RequestException as exc:
            raise ProviderError(f"zimuku 下载失败：{exc}") from exc
        return save_subtitle_bytes(file_response.content, f"{title or subtitle_id}.srt", dest_dir)
