from __future__ import annotations

import base64
import hashlib
import re
import shutil
from pathlib import Path
from typing import Callable
from urllib.parse import unquote, urlparse

from app.models import MediaFile
from app.services.store import Store


MEDIA_EXTENSIONS = {
    ".3gp", ".avi", ".divx", ".flv", ".m2ts", ".m4v", ".mkv", ".mov",
    ".mp4", ".mpeg", ".mpg", ".mts", ".rm", ".rmvb", ".ts", ".webm", ".wmv",
    ".strm",
}
POSTER_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".avif"}
# strm 目标指向的媒体容器后缀
CONTAINER_EXTENSIONS = MEDIA_EXTENSIONS - {".strm"} | {".iso"}
STRM_READ_LIMIT = 4096

# 质量/压制/容器等噪声词,从标题末尾剥离
NOISE = re.compile(
    r"(?ix)(?:\b(?:2160p|1080p|1080i|720p|576p|480p|4k|uhd|hdr10\+?|dv|"
    r"bluray|blu-ray|bdrip|brrip|web[-_. ]?dl|webrip|hdtv|remux|x26[45]|h[._]?26[45]|"
    r"hevc|av1|aac\d?\.\d|dts(?:-hd)?|truehd|atmos|proper|repack|extended|"
    r"dual[-_. ]?audio|multi|internal)\b.*$|\[[^\]]*\]|\{[^}]*\})"
)
EPISODE = re.compile(r"(?i)\bS(\d{1,2})E(\d{1,3})\b")


def clean_title(filename: str, patterns: list[str] | None = None) -> str:
    """从文件名提取媒体标题:先匹配用户正则,再走通用清洗。"""
    stem = Path(filename).stem
    for pattern in patterns or []:
        match = re.search(pattern, stem)
        if match:
            value = match.group(1) if match.lastindex else match.group(0)
            value = value.strip(" -._")
            if value:
                return value
    episode = EPISODE.search(stem)
    cleaned = NOISE.sub("", stem)
    cleaned = re.sub(r"[._]+", " ", cleaned)
    cleaned = re.sub(r"\s*-\s*", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -._")
    if episode and episode.group(0).lower() not in cleaned.lower():
        cleaned = f"{cleaned} S{int(episode.group(1)):02d}E{int(episode.group(2)):02d}"
    return cleaned or stem


def media_id(relative_path: str) -> str:
    return base64.urlsafe_b64encode(relative_path.encode("utf-8")).decode("ascii").rstrip("=")


def decode_media_id(value: str) -> str:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)).decode("utf-8")


def read_strm_target(path: Path) -> str | None:
    """读取 strm 文件内容,返回目标媒体路径或 URL(首个非空行)。"""
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                value = line.strip().lstrip("\ufeff").strip("\"'").strip()
                if value:
                    return value[:STRM_READ_LIMIT]
    except OSError:
        return None
    return None


def strip_container(name: str) -> str:
    suffix = Path(name).suffix.lower()
    if suffix in CONTAINER_EXTENSIONS:
        return name[: -len(suffix)]
    return name


def strm_media_stem(target: str | None) -> str | None:
    """从 strm 目标提取媒体主名(去容器后缀)。支持 URL / 本地路径 / 反斜杠路径。"""
    if not target:
        return None
    parsed = urlparse(target)
    if parsed.scheme and parsed.netloc:
        name = Path(unquote(parsed.path)).name
    else:
        name = target.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
        name = unquote(name)
    if not name:
        return None
    return strip_container(name)


def strm_media_name(path: Path) -> str:
    """strm 媒体主名:优先解析目标文件名,失败回退到 strm 文件名。"""
    stem = strm_media_stem(read_strm_target(path))
    if stem:
        return stem
    return strip_container(path.stem)


def place_subtitle_for_strm(media_root: Path, relative: str, downloaded: Path) -> tuple[Path, str]:
    """把字幕放到 strm 同目录同主名;媒体目录不可写时抛 OSError。"""
    strm_path = (media_root / relative).resolve()
    stem = strm_media_name(strm_path)
    if downloaded.stem.casefold().startswith(stem.casefold()):
        filename = downloaded.name
    else:
        filename = f"{stem}{downloaded.suffix or '.srt'}"
    dest = strm_path.parent / filename
    shutil.move(str(downloaded), str(dest))
    return dest, dest.relative_to(media_root).as_posix()


class MediaLibrary:
    def __init__(
        self,
        root: Path,
        patterns_provider: Callable[[], list[str]] | None = None,
        index_store: Store | None = None,
    ):
        self.root = root.resolve()
        self.patterns_provider = patterns_provider or (lambda: [])
        self.index_store = index_store

    def _poster_path(self, media: Path, stem: str | None = None) -> Path | None:
        images = [p for p in media.parent.iterdir() if p.is_file() and p.suffix.lower() in POSTER_EXTENSIONS]
        if not images:
            return None
        by_stem = {image.stem.casefold(): image for image in images}
        media_stem = (stem or media.stem).casefold()
        preferred = [
            f"{media_stem}-poster", f"{media_stem}.poster", f"{media_stem}_poster",
            media_stem, "poster", "folder", "cover", "movie",
        ]
        for name in preferred:
            if name in by_stem:
                return by_stem[name]
        return images[0] if len(images) == 1 else None

    def _name_for(self, path: Path, is_strm: bool) -> str:
        return strm_media_name(path) if is_strm else path.name

    def scan(self) -> list[MediaFile]:
        if not self.root.exists():
            if self.index_store:
                self.index_store.sync_media_index([])
            return []
        patterns = self.patterns_provider()
        signature = hashlib.sha256("\0".join(patterns).encode("utf-8")).hexdigest()
        cached = self.index_store.get_media_index() if self.index_store else {}
        records: list[dict] = []
        files: list[MediaFile] = []
        for path in self.root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in MEDIA_EXTENSIONS:
                continue
            try:
                stat = path.stat()
                dir_mtime = path.parent.stat().st_mtime_ns
            except OSError:
                continue
            is_strm = path.suffix.lower() == ".strm"
            relative = path.relative_to(self.root).as_posix()
            item_id = media_id(relative)
            previous = cached.get(relative)
            unchanged = bool(
                previous
                and previous["size_bytes"] == stat.st_size
                and previous["mtime_ns"] == stat.st_mtime_ns
                and previous["directory_mtime_ns"] == dir_mtime
                and previous["pattern_signature"] == signature
            )
            if unchanged:
                title = previous["title"]
                poster_relative = previous["poster_path"]
            else:
                name = self._name_for(path, is_strm)
                title = clean_title(name, patterns)
                poster = self._poster_path(path, stem=strm_media_name(path) if is_strm else None)
                poster_relative = poster.relative_to(self.root).as_posix() if poster else None
            files.append(MediaFile(
                id=item_id,
                path=relative,
                filename=path.name,
                title=title,
                poster_url=f"/api/media/{item_id}/poster" if poster_relative else None,
                is_strm=is_strm,
            ))
            records.append({
                "path": relative,
                "media_id": item_id,
                "filename": path.name,
                "title": title,
                "size_bytes": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
                "directory_mtime_ns": dir_mtime,
                "poster_path": poster_relative,
                "pattern_signature": signature,
            })
        if self.index_store:
            self.index_store.sync_media_index(records)
        return sorted(files, key=lambda item: item.path.casefold())

    def get(self, value: str) -> MediaFile:
        relative = decode_media_id(value)
        path = (self.root / relative).resolve()
        try:
            path.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("媒体路径越界") from exc
        if not path.is_file() or path.suffix.lower() not in MEDIA_EXTENSIONS:
            raise FileNotFoundError("媒体文件不存在")
        relative = path.relative_to(self.root).as_posix()
        is_strm = path.suffix.lower() == ".strm"
        name = self._name_for(path, is_strm)
        title = clean_title(name, self.patterns_provider())
        poster = self._poster_path(path, stem=strm_media_name(path) if is_strm else None)
        return MediaFile(
            id=value,
            path=relative,
            filename=path.name,
            title=title,
            poster_url=f"/api/media/{value}/poster" if poster else None,
            is_strm=is_strm,
        )

    def poster_path(self, value: str) -> Path:
        media = self.get(value)
        video = (self.root / media.path).resolve()
        poster = self._poster_path(video, stem=strm_media_name(video) if media.is_strm else None)
        if poster is None:
            raise FileNotFoundError("未找到媒体封面")
        try:
            poster.resolve().relative_to(self.root)
        except ValueError as exc:
            raise ValueError("封面路径越界") from exc
        return poster
