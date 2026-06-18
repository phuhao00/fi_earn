"""本地文件缓存层，减少重复数据请求。"""
import os
import json
import hashlib
import pickle
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from loguru import logger


class DataCache:
    """双层缓存：内存（热数据）+ 磁盘（持久化）。"""

    def __init__(self, cache_dir: str = "./cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        # 内存缓存：key -> (value, saved_at: datetime)
        self._mem: dict[str, tuple[Any, datetime]] = {}
        self._lock = threading.Lock()

    def _key_to_path(self, key: str, suffix: str = ".pkl") -> Path:
        hashed = hashlib.md5(key.encode()).hexdigest()
        return self.cache_dir / f"{hashed}{suffix}"

    def get(self, key: str, ttl_hours: float = 4.0, allow_stale: bool = False) -> Optional[Any]:
        """读取缓存，优先内存层，超过 ttl_hours 返回 None。
        allow_stale=True 时即使过期也返回旧数据（stale-while-revalidate 模式）。
        """
        ttl = timedelta(hours=ttl_hours)
        now = datetime.now()

        # 内存命中
        with self._lock:
            entry = self._mem.get(key)
        if entry is not None:
            value, saved_at = entry
            if now - saved_at <= ttl or allow_stale:
                logger.debug(f"内存缓存命中({'stale' if now - saved_at > ttl else 'fresh'}): {key[:50]}")
                return value
            with self._lock:
                self._mem.pop(key, None)

        # 磁盘命中
        path = self._key_to_path(key)
        meta_path = self._key_to_path(key, ".meta.json")
        if not path.exists() or not meta_path.exists():
            return None
        try:
            with open(meta_path, "r") as f:
                meta = json.load(f)
            saved_at = datetime.fromisoformat(meta["saved_at"])
            expired = now - saved_at > ttl
            if expired and not allow_stale:
                logger.debug(f"磁盘缓存过期: {key[:50]}")
                return None
            with open(path, "rb") as f:
                data = pickle.load(f)
            with self._lock:
                self._mem[key] = (data, saved_at)
            logger.debug(f"磁盘缓存命中({'stale' if expired else 'fresh'}): {key[:50]}")
            return data
        except Exception as e:
            logger.warning(f"读取缓存失败: {e}")
            return None

    def is_fresh(self, key: str, ttl_hours: float) -> bool:
        """判断缓存是否存在且未过期。"""
        return self.get(key, ttl_hours) is not None

    def set(self, key: str, value: Any) -> None:
        """同时写入内存和磁盘。"""
        now = datetime.now()
        with self._lock:
            self._mem[key] = (value, now)

        path = self._key_to_path(key)
        meta_path = self._key_to_path(key, ".meta.json")
        try:
            with open(path, "wb") as f:
                pickle.dump(value, f)
            with open(meta_path, "w") as f:
                json.dump({"saved_at": now.isoformat(), "key": key[:100]}, f)
            logger.debug(f"缓存写入: {key[:50]}")
        except Exception as e:
            logger.warning(f"写入缓存失败: {e}")

    def invalidate(self, key: str) -> None:
        path = self._key_to_path(key)
        meta_path = self._key_to_path(key, ".meta.json")
        for p in [path, meta_path]:
            if p.exists():
                p.unlink()

    def clear_all(self) -> None:
        for f in self.cache_dir.glob("*"):
            f.unlink()
        logger.info("缓存已全部清除")


# 全局缓存实例
_cache_dir = os.getenv("CACHE_DIR", "./cache")
cache = DataCache(_cache_dir)
