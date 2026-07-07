import os
import json
import time
import pytest
from pathlib import Path
from dev_tools.utils import DiskCache

def test_disk_cache_basic(tmp_path):
    # Set up cache dir in tmp_path
    os.environ["DEV_TOOLS_LOG_DIR"] = str(tmp_path)
    # We need to mock get_base_dir or similar if it's used

    cache = DiskCache(subdir="test_cache")
    key = "foo"
    val = {"bar": 123}

    cache.set(key, val)
    assert cache.get(key) == val

    # Test expiration
    cache.set(key, val, ttl=0.1)
    assert cache.get(key) == val
    time.sleep(0.2)
    assert cache.get(key) is None

def test_disk_cache_no_cache():
    cache = DiskCache(subdir="test_cache", no_cache=True)
    cache.set("foo", "bar")
    assert cache.get("foo") is None

def test_disk_cache_clear():
    cache = DiskCache(subdir="test_cache_clear")
    cache.set("a", 1)
    cache.set("b", 2)

    # Check files exist
    files = list(Path(cache.cache_dir).iterdir())
    assert len(files) >= 2

    cache.clear()
    files_after = list(Path(cache.cache_dir).iterdir())
    assert len(files_after) == 0
