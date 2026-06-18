"""本地文件缓存层，减少重复数据请求。"""
import os
import json
import hashlib
import pickle
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from loguru import logger


class DataCache:
    """基于本地文件的数据缓存，支持 DataFrame 和任意 Python 对象。"""

    def __init__(self, cache_dir: str = "./cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _key_to_path(self, key: str, suffix: str = ".pkl") -> Path:
        hashed = hashlib.md5(key.encode()).hexdigest()
        return self.cache_dir / f"{hashed}{suffix}"

    def get(self, key: str, ttl_hours: float = 4.0) -> Optional[Any]:
        """读取缓存，如果超过 ttl_hours 则返回 None。"""
        path = self._key_to_path(key)
        meta_path = self._key_to_path(key, ".meta.json")
        if not path.exists() or not meta_path.exists():
            return None
        try:
            with open(meta_path, "r") as f:
                meta = json.load(f)
            saved_at = datetime.fromisoformat(meta["saved_at"])
            if datetime.now() - saved_at > timedelta(hours=ttl_hours):
                logger.debug(f"缓存过期: {key[:50]}")
                return None
            with open(path, "rb") as f:
                data = pickle.load(f)
            logger.debug(f"缓存命中: {key[:50]}")
            return data
        except Exception as e:
            logger.warning(f"读取缓存失败: {e}")
            return None

    def set(self, key: str, value: Any) -> None:
        """写入缓存。"""
        path = self._key_to_path(key)
        meta_path = self._key_to_path(key, ".meta.json")
        try:
            with open(path, "wb") as f:
                pickle.dump(value, f)
            with open(meta_path, "w") as f:
                json.dump({"saved_at": datetime.now().isoformat(), "key": key[:100]}, f)
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
