# main.py - 程序入口
# 对应 Java 版本的 Main.java

from api_service import ImaApiService
from downloader import FileDownloader
from sync_manager import SyncManager


# ═══════════════════════════════════════════════════════════════
#  ⚙️  请在这里修改配置
# ═══════════════════════════════════════════════════════════════
# 填入你要下载的知识库的 SHARE_ID（从 IMA 分享链接中获取）
SHARE_ID = "30de5690b9cb8ae30600b2f3eb73cda67e8f55d485335db8814990bec870a895"

# 并发下载线程数
DOWNLOAD_THREADS = 20

# 下载根目录（相对于当前工作目录）
DOWNLOAD_ROOT = "downloads"
# ═══════════════════════════════════════════════════════════════


def main():
    print("=" * 60)
    print(" IMA 知识库下载器 (Python 版)")
    print("=" * 60)

    if SHARE_ID.startswith("请填写") or not SHARE_ID.strip():
        print("❌ 错误：请先在 main.py 中修改 SHARE_ID 为你要下载的知识库分享 ID")
        print()
        print("获取方式：")
        print("  1. 打开 IMA 知识库页面")
        print("  2. 点击分享 → 复制链接")
        print("  3. 链接中包含 share_id 参数，填入上方 SHARE_ID 变量")
        return

    # 初始化
    api_service = ImaApiService()
    downloader = FileDownloader(max_workers=DOWNLOAD_THREADS)

    # 启动同步
    manager = SyncManager(api_service, downloader, SHARE_ID, DOWNLOAD_THREADS)
    manager.start_sync(root_dir=DOWNLOAD_ROOT)


if __name__ == "__main__":
    main()
