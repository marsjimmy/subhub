from __future__ import annotations

"""字幕文件保存工具:处理直写、zip 与 7z 解包。"""

import io
import re
import tempfile
import zipfile
from pathlib import Path

from app.providers.base import ProviderError

SUBTITLE_SUFFIXES = {".srt", ".ass", ".ssa", ".sub", ".vtt", ".smi", ".idx", ".sup", ".stl", ".ttml"}
# 文件名非法字符(兼容 Windows 与容器内路径安全)
_ILLEGAL = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_7Z_MAGIC = b"7z\xbc\xaf\x27\x1c"


def sanitize_filename(name: str) -> str:
    name = _ILLEGAL.sub("_", name).strip().strip(".")
    if not name:
        name = "subtitle"
    return name[:180]


def _pick_subtitle(members: list[str]) -> tuple[str, str]:
    """从压缩包成员中选择一个字幕文件,返回 (文件名, 路径)。"""
    files = [m for m in members if not m.endswith("/")]
    candidates = [m for m in files if Path(m).suffix.lower() in SUBTITLE_SUFFIXES]
    pick = candidates or files
    if not pick:
        raise ProviderError("压缩包内没有字幕文件")
    chosen = pick[0]
    return Path(chosen).name, chosen


def _extract_zip(data: bytes, dest_dir: Path) -> Path:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            filename, member = _pick_subtitle(archive.namelist())
            dest = dest_dir / sanitize_filename(filename)
            dest.write_bytes(archive.read(member))
            return dest
    except zipfile.BadZipFile as exc:
        raise ProviderError(f"字幕压缩包损坏：{exc}") from exc


def _extract_7z(data: bytes, dest_dir: Path) -> Path:
    try:
        import py7zr  # 延迟导入,降低非 7z 场景依赖
    except ImportError as exc:
        raise ProviderError("下载到 7z 字幕包,但未安装 py7zr,无法解压") from exc
    try:
        with py7zr.SevenZipFile(io.BytesIO(data)) as archive:
            filename, member = _pick_subtitle(archive.getnames())
            with tempfile.TemporaryDirectory() as tmp:
                archive.extract(path=tmp)
                candidate = Path(tmp) / member
                if not candidate.is_file():
                    # 个别 7z 包成员名含非法路径字符,按 basename 递归定位
                    candidate = next(
                        (p for p in Path(tmp).rglob(Path(member).name) if p.is_file()),
                        None,
                    )
                if not candidate or not candidate.is_file():
                    raise ProviderError("7z 解压后未找到字幕文件")
                dest = dest_dir / sanitize_filename(filename)
                dest.write_bytes(candidate.read_bytes())
                return dest
    except ProviderError:
        raise
    except Exception as exc:
        raise ProviderError(f"7z 字幕包解压失败：{exc}") from exc


def save_subtitle_bytes(data: bytes, suggested_name: str, dest_dir: Path) -> Path:
    """把字幕字节写入 dest_dir,返回最终文件路径。

    - 若是 zip / 7z,解包取第一个字幕文件(命名优先使用压缩包内文件名);
    - 否则按建议文件名直接写入。
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    if data.startswith(b"PK\x03\x04") or data.startswith(b"PK\x05\x06"):
        return _extract_zip(data, dest_dir)
    if data.startswith(_7Z_MAGIC):
        return _extract_7z(data, dest_dir)
    filename = sanitize_filename(suggested_name)
    dest = dest_dir / filename
    dest.write_bytes(data)
    return dest
