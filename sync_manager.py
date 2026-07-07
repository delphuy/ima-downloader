# sync_manager.py - 同步管理器
# 对应 Java 版本的 SyncManager.java，负责递归遍历文件夹和协调下载

from pathlib import Path
from typing import List, Optional

from api_service import ImaApiService
from downloader import FileDownloader, download_single_file
from models import FailedDownload
from traverser import collect_all_files, collect_grouped_files


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
        """启动整个同步和下载过程（使用统一 traverser + download_knowledge_files）。"""
        print("--- Starting Synchronization Process ---")

        try:
            # 使用统一收集器获取 root_name + 带 rel_path 的文件列表
            def on_folder(rel: Path, name: str):
                print(f"📁 {rel}")

            root_name, grouped = collect_grouped_files(
                self.api,
                self.share_id,
                on_folder=on_folder,
            )

            root_path = Path(root_dir) / root_name
            root_path.mkdir(parents=True, exist_ok=True)
            print(f"Root directory: {root_path.resolve()}")
            total = sum(len(v) for v in grouped.values())
            print(f"Found {total} files in {len(grouped)} types. Starting grouped download...")

            # 使用分组下载
            self.downloader.max_category_workers = 3
            failures = self.downloader.download_grouped_files(
                grouped,
                root_path,
                enable_print_pdf=True,
            )
            self._all_failed.extend(failures)

            # 失败重试（串行）
            self._retry_failed()

            self._print_final_report()

        except KeyboardInterrupt:
            print("\n⚠️  Interrupted by user.")
            self._print_final_report()
        except Exception as e:
            print(f"\n❌ Critical error: {e}")

    # 旧的 _process_folder 已由统一的 traverser + download_knowledge_files 替代（见 start_sync）

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


# 工具函数已统一到 downloader.sanitize_name
# traverser.py 负责目录结构收集
