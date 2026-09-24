from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from app.models import SubtitleResult


class ProviderError(RuntimeError):
    """字幕源业务错误(网络、解析、凭据等)。"""


class SubtitleProvider(ABC):
    name: str = ""
    label: str = ""
    # 该源是否依赖外部凭据(如 API token),未配置时自动跳过
    requires_credentials: bool = False

    @property
    def configured(self) -> bool:
        return True

    @abstractmethod
    def search(self, keyword: str) -> list[SubtitleResult]:
        """按关键词搜索字幕,返回结构化结果列表。"""

    @abstractmethod
    def download(self, subtitle_id: str, detail_url: str, title: str, dest_dir: Path) -> Path:
        """下载字幕到 dest_dir,返回最终文件路径(可能是解压后的字幕文件)。"""
