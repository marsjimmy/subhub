"""新增字幕源单元测试:zimuku(验证码放行/解析/下载)与 OpenSubtitles 网页版(FlareSolverr)、7z 解压。

运行:
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import base64
import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.providers.opensubtitles_web import OpenSubtitlesWebProvider
from app.providers.save import save_subtitle_bytes
from app.providers.zimuku import ZimukuProvider

FIXTURES = Path(__file__).parent / "fixtures"

_CAPTCHA_HTML = (
    '<html><head><script>var text="";function stringToHex(s){{return s}}</script></head>'
    '<body><img class="verifyimg" alt="verify_img" src="data:image/bmp;base64,{b64}">'
    '<input name="intext" type="text">security_session_verify</body></html>'
)
_NORMAL_HTML = "<html><body>正常页面内容</body></html>"
_SEARCH_HTML = (
    '<html><body><a href="/search?q=x&chost=zimuku.org">综合搜索</a>'
    '<a href="//zimuku.org/detail/111.html">Movie.2024.1080p.简英.ass</a>'
    '<a href="/detail/222.html">Movie.2024.1080p.国英.ass</a>'
    '<a href="//zimuku.org/subs/333.html">Movie 影片页</a>'
    '</body></html>'
)
_DETAIL_HTML = '<html><body><a href="/dld/111.html">下载</a></body></html>'
_DLD_HTML = (
    '<html><body><a href="/download/MjExfHRva2VufGR0fHJlbW90ZQ%3D%3D/svr/d0">电信高速下载（一）</a>'
    '<a href="/download/MjExfHRva2VufGR0fGxvY2Fs/svr/l0">联通高速下载</a></body></html>'
)


class FakeResponse:
    def __init__(self, text: str = "", json_data: dict | None = None, status: int = 200, content: bytes | None = None):
        self.text = text
        self._json = json_data
        self.status_code = status
        self.apparent_encoding = "utf-8"
        self.content = content if content is not None else text.encode("utf-8")

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> dict:
        if self._json is not None:
            return self._json
        import json as jsonlib
        return jsonlib.loads(self.text)


class FakeOcr:
    def classification(self, image: bytes) -> str:
        return "20710"


class ZimukuTests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = ZimukuProvider("https://zimuku.org", timeout=10)
        self.provider._get_ocr = lambda: FakeOcr()

    def test_captcha_pass_flow(self) -> None:
        """首次请求命中验证码页时,应识别后带 security_verify_img 重试。"""
        captcha_page = _CAPTCHA_HTML.format(b64=base64.b64encode(b"fakebmp").decode())
        calls: list[tuple[str, dict | None]] = []

        def fake_get(url, params=None, timeout=0):
            calls.append((url, params))
            if len(calls) == 1:
                return FakeResponse(text=captcha_page)
            return FakeResponse(text=_NORMAL_HTML)

        self.provider.session.get = fake_get
        response = self.provider._fetch("https://zimuku.org/")
        self.assertEqual(len(calls), 2)
        # hex("20710") = 3230373130
        self.assertEqual(calls[1][1], {"security_verify_img": "3230373130"})
        self.assertIn("正常页面", response.text)

    def test_captcha_failure_raises(self) -> None:
        """放行后仍返回验证码页,应报错而不是静默返回验证码页。"""
        captcha_page = _CAPTCHA_HTML.format(b64=base64.b64encode(b"fakebmp").decode())
        self.provider.session.get = lambda url, params=None, timeout=0: FakeResponse(text=captcha_page)
        with self.assertRaises(Exception):
            self.provider._fetch("https://zimuku.org/")

    def test_search_real_html(self) -> None:
        html_text = (FIXTURES / "zimuku_search.html").read_text(encoding="utf-8", errors="replace")
        self.provider.session.get = lambda url, params=None, timeout=0: FakeResponse(text=html_text)
        results = self.provider.search("十二生肖")
        self.assertGreaterEqual(len(results), 3)
        first = results[0]
        self.assertEqual(first.provider, "zimuku")
        self.assertEqual(first.detail_url, "https://zimuku.org/detail/227762.html")
        self.assertTrue(first.title)

    def test_search_parsing_relative_and_protocol_relative(self) -> None:
        self.provider.session.get = lambda url, params=None, timeout=0: FakeResponse(text=_SEARCH_HTML)
        results = self.provider.search("Movie")
        self.assertEqual(len(results), 2)
        ids = {item.id for item in results}
        self.assertEqual(ids, {"111", "222"})
        by_id = {item.id: item for item in results}
        self.assertEqual(by_id["111"].detail_url, "https://zimuku.org/detail/111.html")
        self.assertEqual(by_id["222"].detail_url, "https://zimuku.org/detail/222.html")

    def test_download_flow(self) -> None:
        """详情页 → dld 页 → 下载线路 → 保存文件。"""
        routes = {
            "https://zimuku.org/detail/111.html": FakeResponse(text=_DETAIL_HTML),
            "https://zimuku.org/dld/111.html": FakeResponse(text=_DLD_HTML),
            "https://zimuku.org/download/MjExfHRva2VufGR0fHJlbW90ZQ%3D%3D/svr/d0": FakeResponse(
                text="1\n00:00:01,000 --> 00:00:02,000\nok\n"
            ),
        }

        def fake_get(url, params=None, timeout=0):
            if url in routes:
                return routes[url]
            return FakeResponse(text=_NORMAL_HTML)

        self.provider.session.get = fake_get
        with tempfile.TemporaryDirectory() as tmp:
            dest = self.provider.download("111", "", "Movie", Path(tmp))
            self.assertTrue(dest.is_file())
            self.assertIn("ok", dest.read_text(encoding="utf-8", errors="replace"))

    def test_download_missing_line_raises(self) -> None:
        self.provider.session.get = lambda url, params=None, timeout=0: FakeResponse(
            text="<html><body>无线路</body></html>"
        )
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(Exception):
                self.provider.download("1", "https://zimuku.org/detail/1.html", "Movie", Path(tmp))


class Save7zTests(unittest.TestCase):
    def test_7z_extract_picks_subtitle(self) -> None:
        try:
            import py7zr
        except ImportError:
            self.skipTest("py7zr 未安装")
        buffer = io.BytesIO()
        with py7zr.SevenZipFile(buffer, "w") as archive:
            archive.writestr("info", "readme.txt")
            archive.writestr("1\nsubtitle-ass", "sub/Movie.zh.ass")
        with tempfile.TemporaryDirectory() as tmp:
            dest = save_subtitle_bytes(buffer.getvalue(), "whatever.srt", Path(tmp))
            self.assertEqual(dest.name, "Movie.zh.ass")
            self.assertEqual(dest.read_text(encoding="utf-8"), "1\nsubtitle-ass")

    def test_7z_without_py7zr_fails_gracefully(self) -> None:
        real_import = __import__("py7zr")
        import builtins

        original = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "py7zr":
                raise ImportError("blocked")
            return original(name, *args, **kwargs)

        builtins.__import__ = fake_import
        try:
            from app.providers.save import _extract_7z

            with self.assertRaises(Exception):
                _extract_7z(b"7z\xbc\xaf\x27\x1c" + b"x" * 64, Path(tempfile.mkdtemp()))
        finally:
            builtins.__import__ = original
        del real_import


class OpenSubtitlesWebTests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = OpenSubtitlesWebProvider(lambda: "http://flaresolverr:8191", timeout=10)

    def test_unconfigured_skipped(self) -> None:
        provider = OpenSubtitlesWebProvider(lambda: "", timeout=10)
        self.assertFalse(provider.configured)

    def test_search_via_flaresolverr(self) -> None:
        """直连被反爬拦截时,应自动走 FlareSolverr 并解析结果。"""
        search_page = (
            '<html><body>'
            '<a href="/zh/subtitles/123">Movie (2024) 1080p 简英</a>'
            '<a href="/en/subtitles/456">Movie 2024 国英</a>'
            '</body></html>'
        )
        flare_payload = {"status": 200, "solution": {"status": 200, "response": search_page}}

        def fake_get(url, timeout=0):
            # 直连:返回反爬拦截页
            return FakeResponse(
                text="<title>Making sure you're not a bot!</title>", status=401
            )

        def fake_post(url, json=None, timeout=0):
            self.assertEqual(url, "http://flaresolverr:8191/v1")
            self.assertEqual(json["cmd"], "request.get")
            return FakeResponse(json_data=flare_payload)

        self.provider.session.get = fake_get
        self.provider.session.post = fake_post
        results = self.provider.search("Movie")
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].detail_url, "https://www.opensubtitles.org/zh/subtitles/123")

    def test_download_binary_via_flaresolverr(self) -> None:
        detail_page = '<html><body><a href="/download/55">下载</a></body></html>'
        flare_payload = {
            "status": 200,
            "solution": {"status": 200, "response": base64.b64encode(b"1\nsub").decode()},
        }

        def fake_get(url, timeout=0):
            if url == "https://www.opensubtitles.org/zh/subtitles/55":
                return FakeResponse(text=detail_page)
            # 直连下载被拦截
            return FakeResponse(text="<title>bot check</title>", status=401)

        def fake_post(url, json=None, timeout=0):
            self.assertEqual(json.get("returnOnlyBase64"), True)
            return FakeResponse(json_data=flare_payload)

        self.provider.session.get = fake_get
        self.provider.session.post = fake_post
        with tempfile.TemporaryDirectory() as tmp:
            dest = self.provider.download("55", "", "Movie", Path(tmp))
            self.assertTrue(dest.is_file())


if __name__ == "__main__":
    unittest.main(verbosity=2)
