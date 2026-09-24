"""SubHub 单元测试(标准库 unittest,无额外依赖)。

运行:
    python -m unittest discover -s tests -v
或:
    python tests/test_subhub.py
"""

from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.providers.save import save_subtitle_bytes, sanitize_filename
from app.providers.subhd import SubhdProvider
from app.services.media_library import (
    MediaLibrary,
    clean_title,
    media_id,
    place_subtitle_for_strm,
    read_strm_target,
    strm_media_stem,
)
from app.services.store import Store

FIXTURES = Path(__file__).parent / "fixtures"


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


class StrmTests(unittest.TestCase):
    def test_strm_media_stem_variants(self) -> None:
        cases = {
            "http://192.168.1.10:8096/videos/123/Movie%20(2012)%201080p.mkv?api_key=abc": "Movie (2012) 1080p",
            "/mnt/cloud/movies/Inception (2010)/Inception (2010).mkv": "Inception (2010)",
            "\\\\server\\share\\TV\\Show.S01E01.mkv": "Show.S01E01",
            "Movies/Movie.mkv": "Movie",
            "Movie": "Movie",
            "file:///data/Movie.mp4": "Movie",
            None: None,
            "": None,
        }
        for target, expected in cases.items():
            self.assertEqual(strm_media_stem(target), expected, target)

    def test_read_strm_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "m.strm"
            path.write_bytes("\ufeff'/mnt/cloud/Movie.mkv'\r\n".encode("utf-8"))
            self.assertEqual(read_strm_target(path), "/mnt/cloud/Movie.mkv")
            path.write_text("", encoding="utf-8")
            self.assertIsNone(read_strm_target(path))

    def test_scan_and_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            movies = root / "Movies"
            movies.mkdir()
            (movies / "Movie.mkv.strm").write_text("/mnt/cloud/Movie (2012).mkv\n", encoding="utf-8")
            (movies / "Movie (2012).jpg").write_bytes(b"jpeg")
            (movies / "Show.S01E01.strm").write_text(
                "http://nas:8096/videos/9/Show.S01E01.1080p.mkv?k=x\n", encoding="utf-8"
            )
            (movies / "sample.mp4").write_bytes(b"data")
            store = Store(Path(tmp) / "subhub.db")
            library = MediaLibrary(root, patterns_provider=store.get_title_patterns, index_store=store)
            items = library.scan()
            self.assertEqual(len(items), 3)
            by_path = {item.path: item for item in items}
            movie = by_path["Movies/Movie.mkv.strm"]
            self.assertTrue(movie.is_strm)
            self.assertEqual(movie.title, "Movie")
            self.assertIsNotNone(movie.poster_url)
            episode = by_path["Movies/Show.S01E01.strm"]
            self.assertTrue(episode.is_strm)
            self.assertEqual(episode.title, "Show S01E01")
            plain = by_path["Movies/sample.mp4"]
            self.assertFalse(plain.is_strm)

            # 索引缓存:未变化时结果一致
            again = library.scan()
            self.assertEqual([i.path for i in items], [i.path for i in again])
            # 修改 strm 目标(mtime 变化)后重新解析
            strm = movies / "Movie.mkv.strm"
            os.utime(strm, (strm.stat().st_atime, strm.stat().st_mtime + 2))
            strm.write_text("/mnt/cloud/Movie 2 (2024).mkv\n", encoding="utf-8")
            third = library.scan()
            changed = next(i for i in third if i.path == "Movies/Movie.mkv.strm")
            self.assertEqual(changed.title, "Movie 2")

            # get 拒绝非媒体文件
            with self.assertRaises(FileNotFoundError):
                library.get(media_id("Movies/Movie (2012).jpg"))


class PlaceSubtitleTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.media = Path(self._tmp.name) / "media"
        self.downloads = Path(self._tmp.name) / "downloads"
        self.media.mkdir()
        self.downloads.mkdir()
        movies = self.media / "Movies"
        movies.mkdir()
        (movies / "Movie.mkv.strm").write_text("/mnt/cloud/Movie (2012).mkv\n", encoding="utf-8")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _download(self, name: str) -> Path:
        path = self.downloads / name
        path.write_text("1\n00:00:01,000 --> 00:00:03,000\nhello\n", encoding="utf-8")
        return path

    def test_keep_language_tag(self) -> None:
        dest, relative = place_subtitle_for_strm(self.media, "Movies/Movie.mkv.strm", self._download("Movie (2012).chs.srt"))
        self.assertEqual(dest.name, "Movie (2012).chs.srt")
        self.assertEqual(relative, "Movies/Movie (2012).chs.srt")

    def test_rename_unrelated(self) -> None:
        dest, _ = place_subtitle_for_strm(self.media, "Movies/Movie.mkv.strm", self._download("download.srt"))
        self.assertEqual(dest.name, "Movie (2012).srt")

    def test_readonly_media_raises(self) -> None:
        movies = self.media / "Movies"
        movies.chmod(0o500)
        try:
            with self.assertRaises(OSError):
                place_subtitle_for_strm(self.media, "Movies/Movie.mkv.strm", self._download("a.srt"))
        finally:
            movies.chmod(0o755)


class SaveTests(unittest.TestCase):
    def test_direct_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dest = save_subtitle_bytes(b"1\nhello", "My.Movie.srt", Path(tmp))
            self.assertEqual(dest.name, "My.Movie.srt")
            self.assertEqual(dest.read_bytes(), b"1\nhello")

    def test_zip_extract_picks_subtitle(self) -> None:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("readme.txt", "info")
            archive.writestr("sub/My.Movie.zh.srt", "1\nsubtitle")
        with tempfile.TemporaryDirectory() as tmp:
            dest = save_subtitle_bytes(buffer.getvalue(), "whatever.srt", Path(tmp))
            self.assertEqual(dest.name, "My.Movie.zh.srt")
            self.assertEqual(dest.read_text(encoding="utf-8"), "1\nsubtitle")

    def test_sanitize(self) -> None:
        self.assertEqual(sanitize_filename('a/b\\c:d*?"<>|.srt'), "a_b_c_d______.srt")
        self.assertNotEqual(sanitize_filename("..."), "...")


class SubhdParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = SubhdProvider("https://subhd.tv", timeout=10)

    def test_search_real_html(self) -> None:
        html_text = (FIXTURES / "subhd_search.html").read_text(encoding="utf-8", errors="replace")
        self.provider.session.get = lambda url, headers=None, timeout=0: FakeResponse(text=html_text)
        results = self.provider.search("十二生肖")
        self.assertGreaterEqual(len(results), 3)
        first = results[0]
        self.assertEqual(first.provider, "subhd")
        self.assertTrue(first.id)
        self.assertEqual(first.detail_url, f"https://subhd.tv/a/{first.id}")
        self.assertTrue(first.title)

    def test_download_via_preview(self) -> None:
        payload = {
            "success": True,
            "file": {"index": 0, "filename": "Movie.zh.ass", "content": "[Script Info]\nTitle: x\n"},
        }
        self.provider.session.get = lambda url, headers=None, timeout=0: FakeResponse(json_data=payload)
        with tempfile.TemporaryDirectory() as tmp:
            dest = self.provider.download("abc123", "https://subhd.tv/a/abc123", "Movie", Path(tmp))
            self.assertEqual(dest.name, "Movie.zh.ass")
            self.assertIn("Script Info", dest.read_text(encoding="utf-8"))

    def test_download_failure(self) -> None:
        self.provider.session.get = lambda url, headers=None, timeout=0: FakeResponse(
            json_data={"success": False, "message": "denied"}
        )
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(Exception):
                self.provider.download("x", "", "Movie", Path(tmp))


class AssrtTests(unittest.TestCase):
    def test_unconfigured_skipped(self) -> None:
        provider = SubhdProvider.__mro__  # noqa: F841  (占位,避免误用)
        from app.providers.assrt import AssrtProvider

        assrt = AssrtProvider("https://api.assrt.net", lambda: "", timeout=10)
        self.assertFalse(assrt.configured)

    def test_search_parsing(self) -> None:
        from app.providers.assrt import AssrtProvider

        payload = {
            "status": 0,
            "data": {
                "search": [
                    {
                        "id": 12345,
                        "filename": "Movie.2024.1080p.简英.ass",
                        "subname": "Movie",
                        "format": "ass",
                        "url": "https://sub.assrt.net/12345.ass",
                    }
                ]
            },
        }
        assrt = AssrtProvider("https://api.assrt.net", lambda: "tok", timeout=10)
        assrt.session.get = lambda url, timeout=0: FakeResponse(json_data=payload)
        results = assrt.search("Movie")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].id, "12345")
        self.assertEqual(results[0].provider, "assrt")
        self.assertEqual(results[0].detail_url, "https://sub.assrt.net/12345.ass")


class OpenSubtitlesTests(unittest.TestCase):
    def test_search_parsing(self) -> None:
        from app.providers.opensubtitles import OpenSubtitlesProvider

        creds = {"api_key": "k", "username": "u", "password": "p"}
        provider = OpenSubtitlesProvider("https://api.opensubtitles.com", lambda: creds, timeout=10)
        provider._token = "fake-token"
        payload = {
            "data": [
                {
                    "id": "9876",
                    "attributes": {
                        "title": "Movie (2024) 1080p",
                        "movie_name": "Movie",
                        "format": "srt",
                        "url": "https://www.opensubtitles.com/en/subtitles/9876",
                        "files": [{"file_id": 55, "file_name": "Movie.srt"}],
                    },
                }
            ]
        }
        provider.session.get = lambda url, params=None, headers=None, timeout=0: FakeResponse(json_data=payload)
        results = provider.search("Movie")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].id, "9876")
        self.assertEqual(results[0].title, "Movie (2024) 1080p")

    def test_download_flow(self) -> None:
        from app.providers.opensubtitles import OpenSubtitlesProvider

        creds = {"api_key": "k", "username": "u", "password": "p"}
        provider = OpenSubtitlesProvider("https://api.opensubtitles.com", lambda: creds, timeout=10)
        provider._token = "fake-token"
        download_response = FakeResponse(json_data={"link": "https://dl.example/sub.zip"})
        calls = {"n": 0}

        def fake_get(url, params=None, headers=None, timeout=0):
            if url.endswith("/sub.zip"):
                return FakeResponse(text="1\n00:00:01,000 --> 00:00:02,000\nok\n")
            raise AssertionError(f"unexpected get {url}")

        provider.session.get = fake_get
        provider.session.post = lambda url, json=None, headers=None, timeout=0: download_response
        with tempfile.TemporaryDirectory() as tmp:
            dest = provider.download("55", "", "Movie", Path(tmp))
            self.assertTrue(dest.is_file())


if __name__ == "__main__":
    unittest.main(verbosity=2)
