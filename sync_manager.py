# sync_manager.py - 同步管理器
# 对应 Java 版本的 SyncManager.java，负责递归遍历文件夹和协调下载

import re
import time
from pathlib import Path
from typing import List, Optional
from models import ShareInfoResponse, KnowledgeItem, FailedDownload
from api_service import ImaApiService
from downloader import FileDownloader, sanitize_filename, download_single_file


class SyncManager:
    """管理整个同步流程：递归获取目录 → 并发下载 → 失败重试。"""

    def __init__(
        self,
        api_service: ImaApiService,
        downloader: FileDownloader,
        share_id: str,
        download_threads: int = 20,
    ):
        self.api = api_service
        self.downloader = downloader
        self.share_id = share_id
        self.download_threads = download_threads

        # 所有层级的失败任务（线程安全）
        self._all_failed: List[FailedDownload] = []

    # ── 公开接口 ───────────────────────────────────────────────

    def start_sync(self, root_dir: str = "downloads") -> None:
        """启动整个同步和下载过程。"""
        print("--- Starting Synchronization Process ---")

        try:
            # 1. 获取根目录信息
            initial_resp = self.api.get_share_info(self.share_id, limit=1, cursor="", folder_id="")
            if initial_resp.code != 0 or not initial_resp.current_path:
                print("❌ Failed to get initial folder info. Aborting.")
                return

            # 2. 创建根目录
            root_name = sanitize_name(initial_resp.current_path[0].name)
            root_path = Path(root_dir) / root_name
            root_path.mkdir(parents=True, exist_ok=True)
            print(f"Root directory: {root_path.resolve()}")

            # 3. 递归处理
            self._process_folder("", root_path)

            # 4. 失败重试（串行）
            self._retry_failed()

            self._print_final_report()

        except KeyboardInterrupt:
            print("\n⚠️  Interrupted by user.")
            self._print_final_report()
        except Exception as e:
            print(f"\n❌ Critical error: {e}")

    # ── 递归处理 ───────────────────────────────────────────────

    def _process_folder(self, folder_id: str, current_dir: Path) -> None:
        """递归处理指定 folderId 的内容，下载文件并继续遍历子文件夹。"""
        print(f"\n📁 Processing folder: {current_dir}")
        items_to_download: List[KnowledgeItem] = []
        subfolders: List[KnowledgeItem] = []

        # 分页获取当前文件夹下的所有条目
        cursor = ""
        page = 0
        while True:
            page += 1
            resp = self.api.get_share_info(
                share_id=self.share_id,
                limit=20,
                cursor=cursor,
                folder_id=folder_id,
            )
            if resp.code != 0:
                print(f"⚠️  Failed to fetch content for folderId={folder_id}, skipping.")
                return

            for item in resp.knowledge_list:
                if item.folder_info is not None:
                    subfolders.append(item)
                else:
                    items_to_download.append(item)

            if resp.is_end or not resp.next_cursor:
                break
            cursor = resp.next_cursor
            time.sleep(0.3)  # 礼貌性延时

        # 下载当前目录的文件
        if items_to_download:
            print(f"  📥 Found {len(items_to_download)} files, downloading...")
            failures = self.downloader.download_files_concurrently(
                items_to_download, current_dir
            )
            self._all_failed.extend(failures)

        # 递归处理子文件夹
        for folder_item in subfolders:
            folder_info = folder_item.folder_info
            sub_dir_name = sanitize_name(folder_info.name)
            sub_dir_path = current_dir / sub_dir_name
            sub_dir_path.mkdir(parents=True, exist_ok=True)
            self._process_folder(folder_info.folder_id, sub_dir_path)

    # ── 失败重试 ───────────────────────────────────────────────

    def _retry_failed(self) -> None:
        """对所有失败任务进行一轮串行重试。"""
        if not self._all_failed:
            print("\n✅ No failures. All downloads were successful.")
            return

        print(f"\n--- Retrying {len(self._all_failed)} Failed Downloads ---")
        still_failing: List[FailedDownload] = []
        to_retry = list(self._all_failed)
        self._all_failed.clear()

        for failed in to_retry:
            try:
                print(f"[RETRY] -> {failed.output_path.name}")
                download_single_file(failed.download_url, failed.output_path)
            except Exception as e:
                print(f"[RETRY FAIL] {failed.output_path.name}: {e}")
                still_failing.append(failed)

        self._all_failed = still_failing

    # ── 报告 ─────────────────────────────────────────────────

    def _print_final_report(self) -> None:
        print("\n--- Final Report ---")
        print(f"Unrecoverable failures: {len(self._all_failed)}")
        if self._all_failed:
            print("List of unrecoverable files:")
            for f in self._all_failed:
                print(f"  - {f.output_path}")
        print("Synchronization process finished.")


# ── 工具函数 ────────────────────────────────────────────────────

def sanitize_name(name: str) -> str:
    """清理文件夹名称，移除非法字符。"""
    if not name:
        return "unnamed_folder"
    return re.sub(r'[\\/:*?"<>|]', "_", name).strip()
