# downloader.py - 文件下载器
# 对应 Java 版本的 FileDownloader.java + KnowledgeProcessor.java

import re
import requests
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Callable, Optional
from models import KnowledgeItem, FailedDownload


# ── URL 提取工具 ────────────────────────────────────────────────

def extract_download_url(jump_url: str) -> str:
    if not jump_url:
        return ""
    marker = "&imaei="
    idx = jump_url.find(marker)
    return jump_url[:idx] if idx != -1 else jump_url


def extract_download_urls(items: List[KnowledgeItem]) -> List[str]:
    urls = []
    for item in items:
        url = extract_download_url(item.jump_url)
        if url:
            urls.append(url)
    return urls


# ── 文件名清理 ─────────────────────────────────────────────────

def sanitize_filename(filename: str) -> str:
    if not filename:
        return "unknown_file"
    return re.sub(r'[\\/:*?"<>|]', "_", filename).strip()


# ── 单文件下载（支持回调日志）──────────────────────────────────

def download_single_file(
    url: str,
    output_path: Path,
    timeout: tuple = (15, 180),
    on_log: Optional[Callable[[str], None]] = None,
) -> None:
    """下载单个文件，失败抛出 IOError。"""
    _log = on_log or print
    _log(f"[DOWNLOADING] -> {output_path.name}")
    with requests.get(url, stream=True, timeout=timeout) as resp:
        resp.raise_for_status()
        total_size = int(resp.headers.get("Content-Length", 0))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
    _log(f"[DONE] {output_path.name} ({_format_size(total_size)})")


def _format_size(size: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"


# ── FileDownloader 类 ───────────────────────────────────────────

class FileDownloader:
    """并发下载文件，管理失败任务。"""

    def __init__(self, max_workers: int = 20, timeout: tuple = (15, 180)):
        self.max_workers = max_workers
        self.timeout = timeout
        self._on_log: Optional[Callable[[str], None]] = None

    def set_logger(self, callback: Callable[[str], None]):
        """设置日志回调函数（GUI 模式下传入）。"""
        self._on_log = callback

    def _log(self, msg: str):
        if self._on_log:
            self._on_log(msg)
        else:
            print(msg)

    def download_files_concurrently(
        self,
        items: List[KnowledgeItem],
        directory: Path,
    ) -> List[FailedDownload]:
        failed: List[FailedDownload] = []
        directory.mkdir(parents=True, exist_ok=True)

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {}
            for item in items:
                url = extract_download_url(item.jump_url)
                safe_name = sanitize_filename(item.title)
                if not url or not safe_name:
                    continue
                out_path = directory / safe_name
                if out_path.exists():
                    self._log(f"[SKIP] {out_path.name}")
                    continue
                fut = executor.submit(self._download_task, url, out_path, safe_name)
                futures[fut] = (url, out_path)

            for fut in as_completed(futures):
                url, out_path = futures[fut]
                exc = fut.exception()
                if exc:
                    self._log(f"[FAIL] {out_path.name} | {exc}")
                    failed.append(FailedDownload(download_url=url, output_path=out_path))

        return failed

    def _download_task(self, url: str, out_path: Path, name: str) -> None:
        with requests.get(url, stream=True, timeout=self.timeout) as resp:
            resp.raise_for_status()
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with out_path.open("wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
        self._log(f"[DONE] {name}")