from __future__ import annotations

import json
import re
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from threading import RLock
from typing import Iterator


DEFAULT_PATTERNS = [r"(.*?)\s*\(\d{4}\)"]
DEFAULT_PROVIDERS = {
    "zimuku": True,
    "subhd": True,
    "assrt": False,
    "opensubtitles": False,
    "opensubtitles_api": False,
}
MAX_PATTERNS = 20
MAX_PATTERN_LENGTH = 300


@contextmanager
def database_connection(path: Path) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def validate_patterns(patterns: list[str]) -> list[str]:
    cleaned: list[str] = []
    if len(patterns) > MAX_PATTERNS:
        raise ValueError(f"最多允许 {MAX_PATTERNS} 条正则")
    for raw in patterns:
        pattern = raw.strip()
        if not pattern or pattern in cleaned:
            continue
        if len(pattern) > MAX_PATTERN_LENGTH:
            raise ValueError(f"单条正则不能超过 {MAX_PATTERN_LENGTH} 个字符")
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ValueError(f"正则格式错误：{pattern}（{exc}）") from exc
        cleaned.append(pattern)
    if not cleaned:
        raise ValueError("至少需要一条媒体名称识别正则")
    return cleaned


def initialize_database(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with database_connection(path) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS title_patterns (
                position INTEGER PRIMARY KEY,
                pattern TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS subtitle_providers (
                name TEXT PRIMARY KEY,
                enabled INTEGER NOT NULL CHECK (enabled IN (0, 1))
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS download_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider TEXT NOT NULL,
                subtitle_id TEXT NOT NULL,
                title TEXT NOT NULL,
                filename TEXT NOT NULL DEFAULT '',
                path TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL CHECK (status IN ('pending', 'success', 'failed')),
                error TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                completed_at TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS search_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                keyword TEXT NOT NULL,
                provider_count INTEGER NOT NULL,
                cache_hits INTEGER NOT NULL,
                result_count INTEGER NOT NULL,
                error_count INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS search_history_providers (
                search_id INTEGER NOT NULL REFERENCES search_history(id) ON DELETE CASCADE,
                provider TEXT NOT NULL,
                PRIMARY KEY (search_id, provider)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS search_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                keyword_key TEXT NOT NULL,
                keyword TEXT NOT NULL,
                provider TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                UNIQUE (keyword_key, provider)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS search_cache_results (
                cache_id INTEGER NOT NULL REFERENCES search_cache(id) ON DELETE CASCADE,
                position INTEGER NOT NULL,
                subtitle_id TEXT NOT NULL,
                title TEXT NOT NULL,
                movie_title TEXT NOT NULL DEFAULT '',
                format TEXT NOT NULL DEFAULT '',
                detail_url TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (cache_id, position)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS media_index (
                path TEXT PRIMARY KEY,
                media_id TEXT NOT NULL UNIQUE,
                filename TEXT NOT NULL,
                title TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                mtime_ns INTEGER NOT NULL,
                directory_mtime_ns INTEGER NOT NULL,
                poster_path TEXT,
                pattern_signature TEXT NOT NULL,
                scanned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_download_history_created ON download_history(created_at DESC)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_search_history_created ON search_history(created_at DESC)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_search_cache_expiry ON search_cache(expires_at)")


class Store:
    """SQLite 持久化:设置、字幕源开关、搜索缓存、下载/搜索历史、媒体索引。"""

    def __init__(self, path: Path):
        self.path = path
        self._lock = RLock()
        initialize_database(path)
        self._seed()

    def _seed(self) -> None:
        with self._lock, database_connection(self.path) as connection:
            count = connection.execute("SELECT COUNT(*) FROM title_patterns").fetchone()[0]
            if not count:
                connection.executemany(
                    "INSERT INTO title_patterns (position, pattern) VALUES (?, ?)",
                    enumerate(DEFAULT_PATTERNS),
                )
            connection.executemany(
                "INSERT OR IGNORE INTO subtitle_providers (name, enabled) VALUES (?, ?)",
                ((name, int(enabled)) for name, enabled in DEFAULT_PROVIDERS.items()),
            )

    # ---------- 标题正则 ----------

    def get_title_patterns(self) -> list[str]:
        with self._lock, database_connection(self.path) as connection:
            rows = connection.execute("SELECT pattern FROM title_patterns ORDER BY position").fetchall()
        try:
            return validate_patterns([row["pattern"] for row in rows])
        except ValueError:
            return DEFAULT_PATTERNS.copy()

    def save_title_patterns(self, patterns: list[str]) -> list[str]:
        cleaned = validate_patterns(patterns)
        with self._lock, database_connection(self.path) as connection:
            connection.execute("DELETE FROM title_patterns")
            connection.executemany(
                "INSERT INTO title_patterns (position, pattern) VALUES (?, ?)",
                enumerate(cleaned),
            )
        return cleaned

    # ---------- 字幕源开关 ----------

    def get_provider_states(self) -> dict[str, bool]:
        with self._lock, database_connection(self.path) as connection:
            rows = connection.execute("SELECT name, enabled FROM subtitle_providers ORDER BY rowid").fetchall()
        return {row["name"]: bool(row["enabled"]) for row in rows}

    def save_provider_states(self, states: dict[str, bool]) -> dict[str, bool]:
        unknown = sorted(set(states) - set(DEFAULT_PROVIDERS))
        if unknown:
            raise ValueError(f"未知字幕源：{', '.join(unknown)}")
        merged = self.get_provider_states()
        merged.update({name: bool(enabled) for name, enabled in states.items()})
        with self._lock, database_connection(self.path) as connection:
            connection.executemany(
                "INSERT OR REPLACE INTO subtitle_providers (name, enabled) VALUES (?, ?)",
                ((name, int(merged[name])) for name in DEFAULT_PROVIDERS),
            )
        return {name: merged[name] for name in DEFAULT_PROVIDERS}

    # ---------- 通用设置项 ----------

    def get_setting(self, key: str, default: str = "") -> str:
        with self._lock, database_connection(self.path) as connection:
            row = connection.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def save_setting(self, key: str, value: str) -> None:
        with self._lock, database_connection(self.path) as connection:
            connection.execute(
                "INSERT OR REPLACE INTO app_settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
                (key, value),
            )

    def clear_setting(self, key: str) -> None:
        with self._lock, database_connection(self.path) as connection:
            connection.execute("DELETE FROM app_settings WHERE key = ?", (key,))

    # ---------- 搜索缓存 ----------

    @staticmethod
    def _keyword_key(keyword: str) -> str:
        return " ".join(keyword.casefold().split())

    def get_search_cache(self, keyword: str, provider: str) -> list[dict] | None:
        now = int(time.time())
        with self._lock, database_connection(self.path) as connection:
            connection.execute("DELETE FROM search_cache WHERE expires_at <= ?", (now,))
            row = connection.execute(
                "SELECT id FROM search_cache WHERE keyword_key = ? AND provider = ? AND expires_at > ?",
                (self._keyword_key(keyword), provider, now),
            ).fetchone()
            if not row:
                return None
            items = connection.execute(
                """
                SELECT subtitle_id, title, movie_title, format, detail_url
                FROM search_cache_results WHERE cache_id = ? ORDER BY position
                """,
                (row["id"],),
            ).fetchall()
        return [
            {
                "provider": provider,
                "id": item["subtitle_id"],
                "title": item["title"],
                "movie_title": item["movie_title"],
                "format": item["format"],
                "detail_url": item["detail_url"],
            }
            for item in items
        ]

    def save_search_cache(self, keyword: str, provider: str, results: list[dict], ttl_seconds: int) -> None:
        now = int(time.time())
        expires_at = now + max(1, ttl_seconds)
        key = self._keyword_key(keyword)
        with self._lock, database_connection(self.path) as connection:
            row = connection.execute(
                "SELECT id FROM search_cache WHERE keyword_key = ? AND provider = ?",
                (key, provider),
            ).fetchone()
            if row:
                cache_id = row["id"]
                connection.execute(
                    "UPDATE search_cache SET keyword = ?, created_at = ?, expires_at = ? WHERE id = ?",
                    (keyword, now, expires_at, cache_id),
                )
                connection.execute("DELETE FROM search_cache_results WHERE cache_id = ?", (cache_id,))
            else:
                cursor = connection.execute(
                    "INSERT INTO search_cache (keyword_key, keyword, provider, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
                    (key, keyword, provider, now, expires_at),
                )
                cache_id = cursor.lastrowid
            connection.executemany(
                """
                INSERT INTO search_cache_results
                    (cache_id, position, subtitle_id, title, movie_title, format, detail_url)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    (
                        cache_id,
                        position,
                        item["id"],
                        item["title"],
                        item.get("movie_title", ""),
                        item.get("format", ""),
                        item.get("detail_url", ""),
                    )
                    for position, item in enumerate(results)
                ),
            )

    def clear_search_cache(self, provider: str | None = None) -> int:
        with self._lock, database_connection(self.path) as connection:
            if provider:
                cursor = connection.execute("DELETE FROM search_cache WHERE provider = ?", (provider,))
            else:
                cursor = connection.execute("DELETE FROM search_cache")
            return cursor.rowcount

    # ---------- 历史 ----------

    def record_search(self, keyword: str, providers: list[str], cache_hits: int, result_count: int, error_count: int) -> int:
        with self._lock, database_connection(self.path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO search_history
                    (keyword, provider_count, cache_hits, result_count, error_count)
                VALUES (?, ?, ?, ?, ?)
                """,
                (keyword, len(providers), cache_hits, result_count, error_count),
            )
            search_id = cursor.lastrowid
            connection.executemany(
                "INSERT INTO search_history_providers (search_id, provider) VALUES (?, ?)",
                ((search_id, provider) for provider in providers),
            )
        return search_id

    def list_search_history(self, limit: int = 100) -> list[dict]:
        with self._lock, database_connection(self.path) as connection:
            rows = connection.execute(
                """
                SELECT id, keyword, provider_count, cache_hits, result_count, error_count, created_at
                FROM search_history ORDER BY id DESC LIMIT ?
                """,
                (max(1, min(limit, 500)),),
            ).fetchall()
            result: list[dict] = []
            for row in rows:
                provider_rows = connection.execute(
                    "SELECT provider FROM search_history_providers WHERE search_id = ? ORDER BY provider",
                    (row["id"],),
                ).fetchall()
                item = dict(row)
                item["providers"] = [provider_row["provider"] for provider_row in provider_rows]
                result.append(item)
        return result

    def start_download(self, provider: str, subtitle_id: str, title: str) -> int:
        with self._lock, database_connection(self.path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO download_history (provider, subtitle_id, title, status)
                VALUES (?, ?, ?, 'pending')
                """,
                (provider, subtitle_id, title),
            )
            return cursor.lastrowid

    def finish_download(self, history_id: int, filename: str, path: str) -> None:
        with self._lock, database_connection(self.path) as connection:
            connection.execute(
                """
                UPDATE download_history
                SET filename = ?, path = ?, status = 'success', error = '', completed_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (filename, path, history_id),
            )

    def fail_download(self, history_id: int, error: str) -> None:
        with self._lock, database_connection(self.path) as connection:
            connection.execute(
                """
                UPDATE download_history
                SET status = 'failed', error = ?, completed_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (error[:2000], history_id),
            )

    def list_download_history(self, limit: int = 100) -> list[dict]:
        with self._lock, database_connection(self.path) as connection:
            rows = connection.execute(
                """
                SELECT id, provider, subtitle_id, title, filename, path, status, error,
                       created_at, completed_at
                FROM download_history ORDER BY id DESC LIMIT ?
                """,
                (max(1, min(limit, 500)),),
            ).fetchall()
        return [dict(row) for row in rows]

    # ---------- 媒体索引 ----------

    def get_media_index(self) -> dict[str, dict]:
        with self._lock, database_connection(self.path) as connection:
            rows = connection.execute(
                """
                SELECT path, media_id, filename, title, size_bytes, mtime_ns,
                       directory_mtime_ns, poster_path, pattern_signature
                FROM media_index
                """
            ).fetchall()
        return {row["path"]: dict(row) for row in rows}

    def sync_media_index(self, records: list[dict]) -> None:
        with self._lock, database_connection(self.path) as connection:
            connection.executemany(
                """
                INSERT INTO media_index
                    (path, media_id, filename, title, size_bytes, mtime_ns,
                     directory_mtime_ns, poster_path, pattern_signature, scanned_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(path) DO UPDATE SET
                    media_id = excluded.media_id,
                    filename = excluded.filename,
                    title = excluded.title,
                    size_bytes = excluded.size_bytes,
                    mtime_ns = excluded.mtime_ns,
                    directory_mtime_ns = excluded.directory_mtime_ns,
                    poster_path = excluded.poster_path,
                    pattern_signature = excluded.pattern_signature,
                    scanned_at = CURRENT_TIMESTAMP
                """,
                (
                    (
                        item["path"], item["media_id"], item["filename"], item["title"],
                        item["size_bytes"], item["mtime_ns"], item["directory_mtime_ns"],
                        item.get("poster_path"), item["pattern_signature"],
                    )
                    for item in records
                ),
            )
            connection.execute("CREATE TEMP TABLE seen_media_paths (path TEXT PRIMARY KEY)")
            connection.executemany(
                "INSERT INTO seen_media_paths (path) VALUES (?)",
                ((record["path"],) for record in records),
            )
            connection.execute(
                "DELETE FROM media_index WHERE NOT EXISTS "
                "(SELECT 1 FROM seen_media_paths WHERE seen_media_paths.path = media_index.path)"
            )

    def database_stats(self) -> dict[str, int]:
        tables = ["download_history", "search_history", "search_cache", "media_index"]
        with self._lock, database_connection(self.path) as connection:
            return {table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in tables}

    # ---------- JSON 迁移辅助(预留) ----------

    def migrate_json(self, legacy_path: Path) -> None:
        if not legacy_path.is_file():
            return
        try:
            data = json.loads(legacy_path.read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return
        if not isinstance(data, dict):
            return
        if "title_patterns" in data:
            try:
                self.save_title_patterns(data["title_patterns"])
            except ValueError:
                pass
        legacy_path.unlink(missing_ok=True)
