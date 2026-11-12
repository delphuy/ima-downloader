# main.py - v1.0.8 命令行入口（GUI 仍是主入口：start.bat → gui.py）
# 流程：扫码登录（已登录则静默续期）→ 匿名遍历分享库 → 原件直下 + 字节级校验
# 旧版 v1.0.7 的 OpenAPI/收割链路已退役（gui.py 不再引用）。

import os
import sys
from pathlib import Path

from api_service import ImaApiService
from ima_auth import get_session, login_flow
from original_minter import run_originals_sync
from traverser import collect_all_files


# ═══════════════════════════════════════════════════════════════
#  ⚙️  请在这里修改配置
# ═══════════════════════════════════════════════════════════════
# 填入你要下载的知识库的 SHARE_ID（分享链接里 shareId= 后面的 64 位串）
SHARE_ID = "30de5690b9cb8ae30600b2f3eb73cda67e8f55d485335db8814990bec870a895"

# 下载根目录（程序会在其下自动创建 <知识库名>/ 子目录）
DOWNLOAD_ROOT = "downloads"

# 并发下载数
WORKERS = 8
# ═══════════════════════════════════════════════════════════════


def main():
    print("=" * 60)
    print(" IMA 知识库下载器 (Python CLI)  v1.0.8 原件直下")
    print("=" * 60)

    if not SHARE_ID.strip() or SHARE_ID.startswith("请填写"):
        print("❌ 请先在 main.py 中填写 SHARE_ID")
        print("  获取方式：知识库页面 → 分享 → 复制链接 → 取 shareId= 后面的 64 位串")
        return

    # 1) 登录态：已保存则静默续期；失效则现场扫码
    sess = get_session()
    if not sess.ensure_fresh(on_log=print):
        print("📱 需要扫码登录……")

        def on_qr(png):
            print(f"📱 二维码已保存：{png}")
            print("   请用微信扫码并在手机上确认")
            try:
                os.startfile(png)
            except Exception:
                pass

        if not login_flow(sess, on_log=print, on_qr=on_qr,
                          cancel_check=None, deadline_s=330):
            print("❌ 登录未完成，退出")
            return

    # 2) 匿名遍历分享库清单
    print("📊 遍历分享库清单……")
    root_name, all_files = collect_all_files(
        ImaApiService(), SHARE_ID,
        on_folder=lambda rel, name: print(f"📁 {rel}"))
    if not root_name:
        print("❌ 获取知识库目录失败")
        return
    targets = [kf for kf in all_files if kf.media_id]
    skipped = len(all_files) - len(targets)
    print(f"共 {len(targets)} 个文件条目" + (f"（另有 {skipped} 个纯链接跳过）" if skipped else ""))

    # 3) 原件直下 + 校验
    root_path = Path(DOWNLOAD_ROOT) / root_name
    last = {"n": -1}

    def on_progress(cur, tot, name):
        if cur != last["n"] and (cur % 10 == 0 or cur == tot):
            last["n"] = cur
            print(f"  [{cur}/{tot}] {name[:44]}")

    report = run_originals_sync(
        sess, targets, root_path, SHARE_ID,
        on_log=print, on_progress=on_progress,
        cancel_check=None, workers=WORKERS)

    print()
    print("📊", report.summary_line())
    for line in report.content_coverage_lines():
        print("   ", line)
    p = report.write_verify_report()
    if p:
        print(f"📋 校验报告: {p}")


if __name__ == "__main__":
    main()
