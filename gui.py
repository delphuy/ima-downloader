# -*- coding: utf-8 -*-
import re
import threading
import urllib.request
import json
import os
import sys
import zipfile
import tempfile
import shutil
import time
from pathlib import Path
from tkinter import Tk, END, DISABLED, NORMAL, filedialog, Text, Toplevel
import tkinter as tk
from tkinter import ttk
import tkinter.scrolledtext as scrolledtext
import tkinter.messagebox as messagebox
from api_service import ImaApiService
from ima_auth import get_session, login_flow
from original_minter import run_originals_sync, OriginalsReport
from traverser import collect_all_files

# ============================================================
# VERSION & UPDATE CONFIG
# ============================================================
__VERSION__ = "1.0.8"
UPDATE_API = "https://api.github.com/repos/delphuy/ima-downloader/releases/latest"
GITHUB_RELEASES = "https://github.com/delphuy/ima-downloader/releases"

# ============================================================
# STRINGS (English / Chinese)
# ============================================================
LANG = {}

LANG["en"] = {
    "title":         "📥 IMA Knowledge Base Downloader",
    "share_label":   "Share Link:",
    "share_ph":      "Open the IMA Knowledge Base, click Share → Copy Link, paste it here\nExample:\n【ima knowledge】Industry Research Report Library https://ima.qq.com/wiki/?shareId=8ccc0a2d2a8cc1c1dbe68d85576e0274e1c99ed344b167e782e9e15befa574a7",
    "dir_label":     "Save Folder:",
    "browse":        "Browse...",
    "start":         "▶ Start Download",
    "cancel":        "⏹ Cancel",
    "ready":         "Ready — paste a share link to begin",
    "preparing":     "Preparing...",
    "update_avail":  "🆕 Update available: v{new_ver} — click to download",
    "no_share_id":   "Cannot extract share_id — check the link",
    "done_ok":       "✅ Download complete",
    "done_fail":     "❌ Download failed",
    "done_full":     "✅ All files downloaded (originals)",
    "done_partial":  "⚠️ Finished — some items limited by server",
    "done_empty":    "❌ Nothing downloaded — server restricted this share",
    "verify_line":   "🔬 Byte-verify: pass {sp} · mismatch {sf} · preview ok {po} · preview bad {pb}",
    "verify_written": "📋 Per-file verification report saved: {path}",
    "cancelled":     "⏹ Cancelled",
    "scan_files":    "Scanning knowledge base...",
    "total_files":   "Found {n} files, starting download",
    "existing":      "Already present: {n} files",
    "folder":        "📁 {name}",
    "btn_login":     "📱 QR Login",
    "login_status_on":  "✅ Logged in (WeChat QR · auto-renews; rescan only when it expires)",
    "login_status_off": "❌ Not logged in — click 'QR Login' and scan with WeChat",
    "login_scanning":   "📱 Generating QR code… scan with WeChat, then confirm on your phone",
    "login_ok":      "✅ Login OK — paste a share link and click Start to get full originals",
    "login_fail":    "❌ Login not completed — click 'QR Login' again",
    "login_required": "❌ Please log in first (click '📱 QR Login' and scan with WeChat)",
    "update_dismiss": "✕",
    "lang_label":    "中文 | EN",
    "btn_check_update": "🔄 Check Update",
    "btn_update":    "⬇ Update",
    "updating":      "⬇ Downloading update v{new_ver}...",
    "update_done":   "✅ Update downloaded! Restart to apply.",
    "update_failed": "❌ Update failed — download manually.",
    "open_github":   "🌐 GitHub",
}

LANG["zh"] = {
    "title":         "📥 IMA 知识库下载器",
    "share_label":   "分享链接:",
    "share_ph":      "找到需要下载的知识库，点击 分享 > 复制链接，将链接粘贴到这里\n例如：\n【ima知识库】行业研究报告库（行研智库） https://ima.qq.com/wiki/?shareId=8ccc0a2d2a8cc1c1dbe68d85576e0274e1c99ed344b167e782e9e15befa574a7",
    "dir_label":     "保存目录:",
    "browse":        "浏览...",
    "start":         "▶ 开始下载",
    "cancel":        "⏹ 取消",
    "ready":         "就绪 — 粘贴分享链接即可开始",
    "preparing":     "准备中...",
    "update_avail":  "🆕 发现新版本 v{new_ver} — 点击自动更新",
    "no_share_id":   "❌ 无法提取 share_id，请检查链接",
    "done_ok":       "✅ 全部下载完成",
    "done_fail":     "❌ 下载失败",
    "done_full":     "✅ 全部原件下载完成",
    "done_partial":  "⚠️ 下载完成 — 部分内容受服务端限制",
    "done_empty":    "❌ 未下载到任何文件 — 服务端限制该分享",
    "verify_line":   "🔬 字节校验: 通过 {sp} · 不符 {sf} · 预览通过 {po} · 预览异常 {pb}",
    "verify_written": "📋 已生成逐文件校验报告: {path}",
    "cancelled":     "⏹ 已取消",
    "scan_files":    "📊 扫描知识库...",
    "total_files":   "共 {n} 个文件，开始下载",
    "existing":      "已存在 {n} 个文件",
    "folder":        "📁 {name}",
    "btn_login":     "📱 扫码登录",
    "login_status_on":  "✅ 已登录（微信扫码 · 票据自动续期，过期才需重扫）",
    "login_status_off": "❌ 未登录 — 点「扫码登录」，用微信扫一下即可",
    "login_scanning":   "📱 正在生成登录二维码……请用微信扫码并在手机上确认",
    "login_ok":      "✅ 登录成功 — 粘贴分享链接，点「开始下载」即可拿完整原件",
    "login_fail":    "❌ 登录未完成，请重新点「扫码登录」",
    "login_required": "❌ 请先扫码登录（点「📱 扫码登录」，用微信扫一下）",
    "update_dismiss": "✕",
    "lang_label":    "中文 | EN",
    "btn_check_update": "🔄 检查更新",
    "btn_update":    "⬇ 更新",
    "updating":      "⬇ 正在下载更新 v{new_ver}...",
    "update_done":   "✅ 更新已下载！请重启程序以应用。",
    "update_failed": "❌ 自动更新失败，请手动下载。",
    "open_github":   "🌐 GitHub",
}


def s(key, **kw):
    return LANG[ImaDownloaderGUI._lang][key].format(**kw)


# ============================================================
# THEME DEFINITIONS (Light default, Dark supported)
# ============================================================
THEMES = {
    "light": {
        "bg": "#f8fafc",
        "surface": "#ffffff",
        "accent": "#6366f1",
        "text": "#1e293b",
        "dim": "#64748b",
        "warn": "#f59e0b",
        "success": "#22c55e",
        "error": "#ef4444",
        "log_bg": "#f1f5f9",
        "entry_bg": "#f8fafc",
        "button_secondary_bg": "#e2e8f0",
    },
    "dark": {
        "bg": "#0f172a",
        "surface": "#1e293b",
        "accent": "#6366f1",
        "text": "#e2e8f0",
        "dim": "#94a3b8",
        "warn": "#f59e0b",
        "success": "#22c55e",
        "error": "#ef4444",
        "log_bg": "#1e293b",
        "entry_bg": "#1e293b",
        "button_secondary_bg": "#334155",
    }
}


# ============================================================
# VERSION CHECKER — silent, no UI notification
# ============================================================
STARTUP_DELAY = 5
_running_checker = None  # FIX 1: 添加缺失的全局变量声明

def start_update_checker(on_version_found):
    global _running_checker
    if _running_checker is not None and _running_checker.is_alive():
        return

    def checker():
        time.sleep(STARTUP_DELAY)
        new_ver = None
        try:
            req = urllib.request.Request(UPDATE_API, headers={"Accept": "application/vnd.github.v3+json"})
            
            # 支持代理：自动检测系统代理环境变量
            proxy_handler = urllib.request.ProxyHandler()
            opener = urllib.request.build_opener(proxy_handler)
            urllib.request.install_opener(opener)
            
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read())
                new_ver = data.get("tag_name", "").lstrip("v")
        except Exception:
            pass

        def notify():
            on_version_found(new_ver)
        ImaDownloaderGUI._root_after(0, notify)

    t = threading.Thread(target=checker, daemon=True)
    t.start()


def download_and_apply_update(zip_url, new_ver, on_done, on_progress, on_open_github):
    def worker():
        tmp_dir = None
        try:
            zip_path = os.path.join(tempfile.gettempdir(), f"ima-update-{new_ver}.zip")

            def report(pct):
                ImaDownloaderGUI._root_after(0, lambda: on_progress(pct))

            report(0)
            # FIX 2: 第一个参数是URL，第二个是保存路径（原错误：两个都是zip_path）
            urllib.request.urlretrieve(zip_url, zip_path,
                                       reporthook=lambda *a: report(min(int(a[2]*100/a[3]), 99)))
            report(99)

            tmp_dir = tempfile.mkdtemp(prefix="ima-update-")
            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(tmp_dir)

            proj_dir = Path(sys.argv[0]).parent.resolve()
            for f in Path(tmp_dir).iterdir():
                dst = proj_dir / f.name
                # FIX 3: 原条件 is_dir() and not is_file() 永远为False，直接改为 is_dir()
                if dst.is_dir():
                    continue
                shutil.copy2(f, dst)

            report(100)
            ImaDownloaderGUI._root_after(0, on_open_github)
            ImaDownloaderGUI._root_after(0, lambda: on_done(True))

        except Exception:
            ImaDownloaderGUI._root_after(0, lambda: on_done(False))
        finally:
            if tmp_dir:
                try:
                    shutil.rmtree(tmp_dir)
                except Exception:
                    pass
            try:
                os.unlink(zip_path)
            except Exception:
                pass

    threading.Thread(target=worker, daemon=True).start()


# ============================================================
# SHARE ID EXTRACTOR
# ============================================================
def extract_share_id(text):
    text = text.strip()
    m = re.search(r'shareId[=:]([a-fA-F0-9]{64})', text)
    if m:
        return m.group(1)
    if re.fullmatch(r'[a-fA-F0-9]{64}', text):
        return text
    return ""


# ============================================================
# DOWNLOAD TASK
# ============================================================
class DownloadTask:
    """v1.0.8: 扫码登录 + 加密信封原件直下（零客户端依赖）。

    流程：匿名遍历分享库拿清单 → 登录态逐个签发原件地址 → 下载 → 字节级校验。
    """

    def __init__(self, share_id, root_dir, on_log, on_progress, on_done,
                 multi_thread=True):
        self.share_id = share_id
        self.root_dir = root_dir
        self.on_log = on_log
        self.on_progress = on_progress
        self.on_done = on_done
        self.multi_thread = multi_thread
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def is_cancelled(self):
        return self._cancelled

    def run(self):
        """执行下载，回调 on_done(result)。

        result 语义：
          - OriginalsReport：正常结束（GUI 按 downloaded/skipped/failed 分档）
          - "cancelled"：用户取消
          - False：异常失败
        """
        try:
            sess = get_session()
            if not sess.ensure_fresh(on_log=self.on_log):
                self.on_log("❌ 登录态已失效，请重新点「📱 扫码登录」")
                self.on_done(False)
                return
            report = self._scan_and_download(sess)
            if self._cancelled:
                self.on_done("cancelled")
            else:
                self.on_done(report)
        except Exception as e:
            self.on_log(f"[错误] {e}")
            self.on_done(False)

    def _scan_and_download(self, sess) -> OriginalsReport:
        # 1) 匿名遍历分享库（列表本身无需登录）
        api = ImaApiService()

        def on_folder(rel, name):
            self.on_log(f"📁 {rel}")

        root_name, all_files = collect_all_files(
            api,
            self.share_id,
            on_folder=on_folder,
            cancel_check=self.is_cancelled,
        )
        if self._cancelled:
            self.on_log(s("cancelled"))
            return OriginalsReport()
        if not root_name:
            self.on_log("❌ 获取知识库目录失败")
            return OriginalsReport()

        root_path = Path(self.root_dir) / root_name
        root_path.mkdir(parents=True, exist_ok=True)
        self.on_log(s("folder", name=root_name))

        # 2) 有 media_id 的条目才能签发原件（链接类无文件实体）
        targets = [kf for kf in all_files if kf.media_id]
        no_mid = len(all_files) - len(targets)
        if no_mid:
            self.on_log(f"⚠️ {no_mid} 个条目无文件实体（纯链接），跳过")
        self.on_log(s("total_files", n=len(targets)))

        # 3) 登录态批量签发 + 下载 + 校验
        report = run_originals_sync(
            sess, targets, root_path, self.share_id,
            on_log=self.on_log,
            on_progress=self.on_progress,
            cancel_check=self.is_cancelled,
            workers=8 if self.multi_thread else 3,
        )
        if self._cancelled:
            self.on_log(s("cancelled"))
        return report


# ============================================================
# GUI
# ============================================================
class ImaDownloaderGUI:
    _lang = "zh"          # default to Chinese
    _root_after = None

    def _safe_after(self, ms, fn):
        """root.after 包装：窗口销毁/主循环未跑时静默放弃，不炸后台线程。"""
        try:
            return self.root.after(ms, fn)
        except Exception:
            return None

    def __init__(self):
        self.root = Tk()
        self.root.withdraw()  # hide until fully configured to prevent flash at default position
        self.root.geometry("950x680")  # set early size to avoid default small/long window
        ImaDownloaderGUI._root_after = self._safe_after
        self.root.title("IMA Knowledge Base Downloader")
        self._task = None
        self._has_placeholder = True
        self._update_dismissed = False
        self._new_ver = None
        self.current_theme = "light"  # Default light mode as per spec

        # Load persisted theme
        try:
            if os.path.exists("theme.txt"):
                with open("theme.txt") as f:
                    saved = f.read().strip()
                    if saved in ("light", "dark"):
                        self.current_theme = saved
        except:
            pass

        # All widgets that need language refresh
        self._widgets = {}

        # Checkboxes for options (default checked)
        self.multi_thread_var = tk.BooleanVar(value=True)
        self.multi_thread_var.trace_add("write", self._on_multi_thread_changed)

        self._build_ui()
        self.apply_theme(self.current_theme)  # Apply (light by default)
        self._on_multi_thread_changed()  # set initial visibility based on checkbox
        self._entry_dir.insert(0, str(Path("downloads").resolve()))
        self._refresh_login_status()  # v1.0.8: 打开即按已存票据同步显示登录状态
        self._startup_session_check()  # v1.0.8: 恢复登录态（静默续期，不阻塞 UI）

        self._center_window()

        # Show ready silently, start background update check after 5s
        self._widgets["lbl_progress"].configure(text=s("ready"))
        start_update_checker(on_version_found=self._on_version_found)

    # ----------------------------------------------------------------
    # BUILD UI
    # ----------------------------------------------------------------
    def _build_ui(self):
        self.root.configure(bg="#f8fafc")  # temporary, will be overridden by apply_theme

        # 应用 ttk 样式 (will be reconfigured in apply_theme)
        style = ttk.Style()
        style.theme_use("clam")

        # Define flat button styles (no borders)
        style.configure("Flat.TButton", relief="flat", borderwidth=0, padding=(8, 5), font=("Microsoft YaHei", 10))
        style.configure("PrimaryFlat.TButton", relief="flat", borderwidth=0, padding=(10, 6), font=("Microsoft YaHei", 11, "bold"))

        # ── Update banner ──
        bar = ttk.Frame(self.root)
        bar.pack(fill="x", padx=12, pady=(8, 0))
        bar.pack_forget()
        self._update_bar = bar

        self._widgets["lbl_update"] = ttk.Label(bar, text="", style="TLabel")
        self._widgets["lbl_update"].pack(side="left", padx=8)

        btn_row = ttk.Frame(bar)
        btn_row.pack(side="right", padx=4)
        self._widgets["btn_update"] = ttk.Button(btn_row, text=s("btn_update"), style="PrimaryFlat.TButton", command=self._do_update)
        self._widgets["btn_update"].pack(side="left", padx=2)
        self._widgets["btn_github"] = ttk.Button(btn_row, text=s("open_github"), style="Flat.TButton", command=self._open_github)
        self._widgets["btn_github"].pack(side="left", padx=2)
        self._widgets["btn_dismiss"] = ttk.Button(btn_row, text=s("update_dismiss"), style="Flat.TButton", command=self._dismiss_update)
        self._widgets["btn_dismiss"].pack(side="left", padx=2)

        # ── Header ──
        header = ttk.Frame(self.root)
        header.pack(fill="x", padx=16, pady=(4, 2))
        self._widgets["lbl_title"] = ttk.Label(header, text=s("title"), style="Title.TLabel")
        self._widgets["lbl_title"].pack(side="left")

        self._widgets["btn_lang"] = ttk.Button(header, text=s("lang_label"), style="Flat.TButton", command=self._toggle_lang)
        self._widgets["btn_lang"].pack(side="right", padx=4)
        self._widgets["btn_check_update"] = ttk.Button(header, text=s("btn_check_update"), style="Flat.TButton", command=self._check_update_manually)
        self._widgets["btn_check_update"].pack(side="right", padx=4)

        # Theme toggle button (added per spec)
        self._widgets["btn_theme"] = ttk.Button(header, text="☀️ 浅色", style="Flat.TButton", command=self.toggle_theme)
        self._widgets["btn_theme"].pack(side="right", padx=4)

        # ── Input Card ──
        card = ttk.Frame(self.root, style="Card.TFrame", padding=12)
        card.pack(fill="x", padx=12, pady=4)

        ttk.Label(card, text=s("share_label")).pack(anchor="w", pady=(0, 2))
        self._text_share = Text(card, font=("Microsoft YaHei", 10), relief="flat", padx=8, pady=6,
                                height=4, wrap="word")
        self._text_share.pack(fill="x")
        self._text_share.insert("1.0", s("share_ph"))
        self._text_share.bind("<FocusIn>", self._on_share_focus_in)
        self._text_share.bind("<FocusOut>", self._on_share_focus_out)

        dir_frame = ttk.Frame(card)
        dir_frame.pack(fill="x", pady=(6, 0))
        ttk.Label(dir_frame, text=s("dir_label")).pack(side="left")
        self._entry_dir = ttk.Entry(dir_frame, font=("Consolas", 10))
        self._entry_dir.pack(side="left", fill="x", expand=True, padx=(8, 4), ipady=3)
        self._widgets["btn_browse"] = ttk.Button(dir_frame, text=s("browse"), style="Flat.TButton", command=self._browse)
        self._widgets["btn_browse"].pack(side="right")

        # ── v1.0.8: 扫码登录行（取代 v1.0.4 OpenAPI 凭证区）──
        login_frame = ttk.Frame(card)
        login_frame.pack(fill="x", pady=(6, 0))
        self._widgets["btn_login"] = ttk.Button(login_frame, text=s("btn_login"),
                                                style="PrimaryFlat.TButton",
                                                command=self._do_qr_login)
        self._widgets["btn_login"].pack(side="left")
        self._widgets["lbl_login_status"] = ttk.Label(
            login_frame, text=s("login_status_off"), style="TLabel",
            font=("Microsoft YaHei", 9))
        self._widgets["lbl_login_status"].pack(side="left", padx=(10, 0))

        btns = ttk.Frame(card)
        btns.pack(pady=(8, 2))

        # Checkboxes left of Start button
        cb_multi = ttk.Checkbutton(btns, text="多线程", variable=self.multi_thread_var, style="TCheckbutton")
        cb_multi.pack(side="left", padx=(0, 8))
        self._widgets["cb_multi"] = cb_multi

        self._widgets["btn_start"] = ttk.Button(btns, text=s("start"), style="PrimaryFlat.TButton", command=self._start, width=18)
        self._widgets["btn_start"].pack(side="left", padx=6)
        self._widgets["btn_cancel"] = ttk.Button(btns, text=s("cancel"), style="Flat.TButton", command=self._cancel, width=12)
        self._widgets["btn_cancel"].pack(side="left", padx=6)

        # Explanation text below buttons - full width, minimal wrap, tight
        note_text = ("v1.0.8 新流程：点「📱 扫码登录」用微信扫码（一次登录 30 天内免重复登录）→ 粘贴分享链接 → 点「开始下载」，"
                     "即可下载每个文档的完整原件（PDF/Word/图片均为原件字节，非首页预览）。"
                     "下载完自动做字节数 + 文件类型双重校验并生成校验报告；已下载过的文件再次运行会自动跳过（增量续传）。"
                     "勾选多线程下载更快，电脑资源紧张时可取消勾选。")
        note_label = ttk.Label(card, text=note_text, font=("Microsoft YaHei", 8), wraplength=900, foreground="#64748b")
        note_label.pack(fill="x", pady=(2, 0))
        self._widgets["note_label"] = note_label

        # ── Progress ──
        prog_frame = ttk.Frame(self.root)
        prog_frame.pack(fill="x", padx=16, pady=(2, 1))
        self._widgets["lbl_progress"] = ttk.Label(prog_frame, text=s("ready"), font=("Consolas", 11, "bold"))
        self._widgets["lbl_progress"].pack(anchor="w")

        self._progress_bar = ttk.Progressbar(prog_frame, mode="determinate", maximum=100)
        self._progress_bar.pack(fill="x", pady=(4, 0))

        # ── Log ──
        log_label = ttk.Label(self.root, text="日志", font=("Microsoft YaHei", 9))
        log_label.pack(anchor="w", padx=16, pady=(2, 1))

        self._log_widget = scrolledtext.ScrolledText(
            self.root, font=("Consolas", 9), relief="flat", padx=8, pady=3
        )
        self._log_widget.pack(fill="both", expand=True, padx=12, pady=(0, 6))
        self._log_widget.tag_configure("ok", foreground="#22c55e")
        self._log_widget.tag_configure("warn", foreground="#f59e0b")
        self._log_widget.tag_configure("err", foreground="#ef4444")
        self._log_widget.tag_configure("pdf", foreground="#6366f1")

    def apply_theme(self, theme_name):
        """Apply light or dark theme (per spec)."""
        if theme_name not in THEMES:
            theme_name = "light"
        self.current_theme = theme_name
        theme = THEMES[theme_name]

        self.root.configure(bg=theme["bg"])

        style = ttk.Style()
        # Base
        style.configure("TFrame", background=theme["surface"])
        style.configure("Card.TFrame", background=theme["surface"])
        style.configure("TLabel", background=theme["surface"], foreground=theme["text"], font=("Microsoft YaHei", 10))
        style.configure("Title.TLabel", background=theme["bg"], foreground=theme["accent"], font=("Microsoft YaHei", 16, "bold"))
        style.configure("TLabelframe.Label", background=theme["surface"], foreground=theme["dim"], font=("Microsoft YaHei", 9))
        style.configure("TLabelframe", background=theme["surface"], foreground=theme["text"])
        style.configure("TLabelframe.Label", background=theme["surface"], foreground=theme["dim"], font=("Microsoft YaHei", 9))

        # Flat buttons (no borders)
        style.configure("Flat.TButton",
            background=theme["button_secondary_bg"],
            foreground=theme["text"],
            relief="flat",
            borderwidth=0,
            padding=(6, 4),
            font=("Microsoft YaHei", 10)
        )
        style.map("Flat.TButton",
            background=[("active", theme["accent"]), ("pressed", theme["accent"])],
            foreground=[("active", "white"), ("pressed", "white")]
        )

        style.configure("PrimaryFlat.TButton",
            background=theme["accent"],
            foreground="white",
            relief="flat",
            borderwidth=0,
            padding=(8, 5),
            font=("Microsoft YaHei", 10, "bold")
        )
        style.map("PrimaryFlat.TButton",
            background=[("active", "#4f46e5"), ("pressed", "#4338ca")]
        )

        # Style for checkboxes to better match flat UI
        style.configure("TCheckbutton",
            background=theme["surface"],
            foreground=theme["text"],
            font=("Microsoft YaHei", 10),
            relief="flat",
            borderwidth=0,
            padding=2,
            indicatorbackground=theme["surface"],
            indicatorforeground=theme["accent"]
        )
        style.map("TCheckbutton",
            background=[("active", theme["surface"])],
            foreground=[("active", theme["accent"])],
            indicatorbackground=[("selected", theme["accent"]), ("active", theme["surface"])]
        )

        style.configure("TEntry", fieldbackground=theme["entry_bg"], foreground=theme["text"], font=("Consolas", 11))
        style.configure("Horizontal.TProgressbar", background=theme["accent"], troughcolor=theme["log_bg"])

        # Raw widgets
        self._text_share.configure(bg=theme["log_bg"], fg=theme["text"], insertbackground=theme["accent"])
        self._log_widget.configure(bg=theme["log_bg"], fg=theme["text"])

        # Update toggle button text
        if "btn_theme" in self._widgets:
            self._widgets["btn_theme"].configure(text="🌙 深色" if theme_name == "light" else "☀️ 浅色")

        # Refresh placeholder color if active
        if hasattr(self, '_has_placeholder') and self._has_placeholder:
            self._text_share.configure(fg=theme["dim"])

        # Force style on checkboxes
        for cb_key in ["cb_multi"]:
            if cb_key in self._widgets:
                self._widgets[cb_key].configure(style="TCheckbutton")

        # Update note color and font
        if "note_label" in self._widgets:
            self._widgets["note_label"].configure(foreground=theme["dim"], font=("Microsoft YaHei", 8))
        if "lbl_login_status" in self._widgets:
            self._widgets["lbl_login_status"].configure(foreground=theme["dim"])

    def _on_multi_thread_changed(self, *args):
        # v1.0.8: 多线程只影响下载并发数（8 vs 3），不再切换分类进度区
        pass

    def _center_window(self):
        self.root.update_idletasks()
        # Wider window, better center (slightly above center for titlebar/taskbar)
        width = 1000
        height = 650
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = max(20, (self.root.winfo_screenheight() // 2) - (height // 2) - 30)
        self.root.geometry(f'{width}x{height}+{x}+{y}')
        self.root.deiconify()  # show after fully positioned to prevent initial flash at default (left) position

    def toggle_theme(self):
        new_theme = "dark" if self.current_theme == "light" else "light"
        self.apply_theme(new_theme)
        # Persist
        try:
            with open("theme.txt", "w") as f:
                f.write(new_theme)
        except:
            pass

    # ----------------------------------------------------------------
    # LANGUAGE TOGGLE — refresh all UI strings
    # ----------------------------------------------------------------
    def _toggle_lang(self):
        ImaDownloaderGUI._lang = "zh" if self._lang == "en" else "en"

        w = self._widgets
        w["lbl_title"].configure(text=s("title"))
        w["lbl_progress"].configure(text=s("ready"))
        w["btn_lang"].configure(text=s("lang_label"))
        w["btn_check_update"].configure(text=s("btn_check_update"))
        w["btn_browse"].configure(text=s("browse"))
        w["btn_start"].configure(text=s("start"))
        w["btn_cancel"].configure(text=s("cancel"))
        w["btn_update"].configure(text=s("btn_update"))
        w["btn_github"].configure(text=s("open_github"))
        w["btn_dismiss"].configure(text=s("update_dismiss"))

        # v1.0.8: 刷新登录行文案
        if "btn_login" in w:
            w["btn_login"].configure(text=s("btn_login"))
        if "lbl_login_status" in w:
            logged = get_session().is_logged_in()
            w["lbl_login_status"].configure(
                text=s("login_status_on" if logged else "login_status_off"))

        # Refresh share text placeholder (keep current content unless it was placeholder)
        was_placeholder = self._has_placeholder
        cur = self._text_share.get("1.0", END).strip()
        self._text_share.delete("1.0", END)
        theme = THEMES[self.current_theme]
        if was_placeholder or not cur:
            self._text_share.insert("1.0", s("share_ph"))
            self._text_share.configure(fg=theme["dim"])
            self._has_placeholder = True
        else:
            self._text_share.insert("1.0", cur)
            self._text_share.configure(fg=theme["text"])
            self._has_placeholder = False

        # Re-apply theme to ensure all colors are correct after language change
        self.apply_theme(self.current_theme)

    # ----------------------------------------------------------------
    # UPDATE CHECK
    # ----------------------------------------------------------------
    # FIX 6: 移除未使用的 err_msg=None 参数
    def _on_version_found(self, new_ver):
        if new_ver and self._compare_ver(new_ver):
            self._new_ver = new_ver
            self._widgets["lbl_update"].configure(text=s("update_avail", new_ver=new_ver))
            # 使用 before 参数确保显示在标题栏之前
            self._update_bar.pack(fill="x", padx=12, pady=(8, 0), side="top", before=self._widgets["lbl_title"].master)

    def _compare_ver(self, new_ver):
        def v(vstr):
            return [int(x) for x in vstr.split(".") if x.isdigit()]
        try:
            nv, cv = v(new_ver), v(__VERSION__)
            for a, b in zip(nv, cv):
                if a > b:
                    return True
                if a < b:
                    return False
            return len(nv) > len(cv)
        except Exception:
            return False

    def _dismiss_update(self):
        self._update_dismissed = True
        self._update_bar.pack_forget()

    def _check_update_manually(self):
        self._widgets["btn_check_update"].configure(state=DISABLED, text="🔄 ...")
        
        def manual_checker():
            new_ver = None
            try:
                req = urllib.request.Request(UPDATE_API, headers={"Accept": "application/vnd.github.v3+json"})
                proxy_handler = urllib.request.ProxyHandler()
                opener = urllib.request.build_opener(proxy_handler)
                urllib.request.install_opener(opener)
                
                with urllib.request.urlopen(req, timeout=60) as resp:
                    data = json.loads(resp.read())
                    new_ver = data.get("tag_name", "").lstrip("v")
            except Exception:
                pass

            def notify():
                if new_ver and self._compare_ver(new_ver):
                    self._new_ver = new_ver
                    self._widgets["lbl_update"].configure(text=s("update_avail", new_ver=new_ver))
                    # 使用 before 参数确保显示在标题栏之前
                    self._update_bar.pack(fill="x", padx=12, pady=(8, 0), side="top", before=self._widgets["lbl_title"].master)
                    self._widgets["lbl_progress"].configure(text=s("update_avail", new_ver=new_ver))
                else:
                    self._widgets["lbl_progress"].configure(text="✅ 已是最新版本")
                self._widgets["btn_check_update"].configure(state=NORMAL, text=s("btn_check_update"))
            
            ImaDownloaderGUI._root_after(0, notify)
        
        threading.Thread(target=manual_checker, daemon=True).start()

    def _open_github(self):
        import webbrowser
        webbrowser.open(GITHUB_RELEASES)

    def _do_update(self):
        if not self._new_ver:
            return
        new_ver = self._new_ver
        self._widgets["lbl_progress"].configure(text=s("updating", new_ver=new_ver))
        self._widgets["btn_update"].configure(state=DISABLED, text="⬇ ...")
        self._widgets["btn_github"].configure(state=DISABLED)
        self._widgets["btn_dismiss"].configure(state=DISABLED)

        def on_progress(pct):
            ImaDownloaderGUI._root_after(0, lambda: self._widgets["lbl_progress"].configure(
                text=f"{s('updating', new_ver=new_ver)} [{pct}%]"))

        def on_done(ok):
            ImaDownloaderGUI._root_after(0, lambda: self._finish_update(ok, new_ver))

        zip_url = f"https://github.com/delphuy/ima-downloader/releases/download/{new_ver}/ima-downloader-{new_ver}.zip"
        download_and_apply_update(zip_url, new_ver, on_done, on_progress, self._open_github)

    def _finish_update(self, ok, new_ver):
        if ok:
            self._widgets["lbl_progress"].configure(text=s("update_done"))
            self._add_log(s("update_done"))
        else:
            self._widgets["lbl_progress"].configure(text=s("update_failed"))
            self._widgets["btn_update"].configure(state=NORMAL, text=s("btn_update"))
            self._widgets["btn_github"].configure(state=NORMAL)
            self._widgets["btn_dismiss"].configure(state=NORMAL)

    # ----------------------------------------------------------------
    # INPUT HELPERS
    # ----------------------------------------------------------------
    def _on_share_focus_in(self, _):
        if self._has_placeholder:
            self._text_share.delete("1.0", END)
            theme = THEMES[self.current_theme]
            self._text_share.configure(fg=theme["text"])
            self._has_placeholder = False

    def _on_share_focus_out(self, _):
        content = self._text_share.get("1.0", END).strip()
        if not content:
            self._text_share.delete("1.0", END)
            self._text_share.insert("1.0", s("share_ph"))
            theme = THEMES[self.current_theme]
            self._text_share.configure(fg=theme["dim"])
            self._has_placeholder = True

    def _get_share_text(self):
        if self._has_placeholder:
            return ""
        return self._text_share.get("1.0", END).strip()

    def _browse(self):
        p = filedialog.askdirectory()
        if p:
            self._entry_dir.delete(0, END)
            self._entry_dir.insert(0, p)

    def _set_ui(self, enabled):
        s_state = NORMAL if enabled else DISABLED
        self._text_share.configure(state=s_state)
        self._entry_dir.configure(state=s_state)
        self._widgets["btn_browse"].configure(state=s_state)
        self._widgets["btn_start"].configure(state=s_state)
        self._widgets["btn_cancel"].configure(state=s_state)
        if "cb_multi" in self._widgets:
            self._widgets["cb_multi"].configure(state=s_state)
        # v1.0.8: 下载期间锁定扫码登录按钮
        if "btn_login" in self._widgets:
            self._widgets["btn_login"].configure(state=s_state)

    # ----------------------------------------------------------------
    # v1.0.8: 扫码登录（微信 QR → ima 票据，一次登录 30 天免登）
    # ----------------------------------------------------------------
    def _do_qr_login(self):
        self._widgets["btn_login"].configure(state=DISABLED)
        self._widgets["lbl_progress"].configure(text=s("login_scanning"))
        self._qr_win = None
        self._qr_img = None

        def on_qr(png_path):
            def show():
                # 优先在软件内弹出二维码窗口（和浏览器登录页同一张图）
                try:
                    img = tk.PhotoImage(file=png_path)
                    win = Toplevel(self.root)
                    win.title(s("btn_login"))
                    win.attributes("-topmost", True)
                    win.resizable(False, False)
                    tk.Label(win, image=img, bg="white").pack(padx=16, pady=(16, 4))
                    tk.Label(win, text=s("login_scanning"),
                             font=("Microsoft YaHei", 10)).pack(pady=(0, 14))
                    self._qr_win = win
                    self._qr_img = img  # 防止 PhotoImage 被回收
                    self._add_log("📱 二维码已在窗口中弹出，微信扫一下、手机上点「确认」")
                except Exception:
                    try:
                        os.startfile(png_path)  # 兜底：系统看图工具打开
                        self._add_log(f"📱 二维码已生成：{png_path}")
                    except Exception:
                        pass
            ImaDownloaderGUI._root_after(0, show)

        def worker():
            sess = get_session()

            def tl(msg):
                ImaDownloaderGUI._root_after(0, lambda m=msg: self._add_log(m))

            ok = login_flow(sess, on_log=tl, on_qr=on_qr,
                            cancel_check=None, deadline_s=330)

            def done():
                if self._qr_win is not None:
                    try:
                        self._qr_win.destroy()
                    except Exception:
                        pass
                    self._qr_win = None
                self._refresh_login_status()
                self._widgets["btn_login"].configure(state=NORMAL)
                self._widgets["lbl_progress"].configure(
                    text=s("login_ok") if ok else s("login_fail"))
            ImaDownloaderGUI._root_after(0, done)

        threading.Thread(target=worker, daemon=True).start()

    def _refresh_login_status(self):
        """刷新登录状态标签（主线程调用）。"""
        if "lbl_login_status" not in self._widgets:
            return
        if get_session().is_logged_in():
            self._widgets["lbl_login_status"].configure(text=s("login_status_on"))
        else:
            self._widgets["lbl_login_status"].configure(text=s("login_status_off"))

    def _startup_session_check(self):
        """启动时后台静默检查/续期票据，不阻塞 UI；完成后刷新状态标签。"""
        def worker():
            sess = get_session()
            if sess.is_logged_in():
                def tl(msg):
                    ImaDownloaderGUI._root_after(0, lambda m=msg: self._add_log(msg))
                try:
                    sess.ensure_fresh(on_log=tl)
                except Exception:
                    pass
            ImaDownloaderGUI._root_after(0, self._refresh_login_status)
        threading.Thread(target=worker, daemon=True).start()

    def _add_log(self, msg):
        """线程安全日志：任何线程调用都转主线程执行（v1.0.8）。"""
        ImaDownloaderGUI._root_after(0, lambda: self._append_log(msg))

    def _append_log(self, msg):
        self._log_widget.configure(state="normal")
        self._log_widget.insert(END, msg + "\n")
        self._log_widget.configure(state="disabled")

    def _on_progress(self, current, total, name):
        pct = int(current * 100 / total) if total > 0 else 0
        def update():
            self._widgets["lbl_progress"].configure(text=f"[{current}/{total}] {name}")
            self._progress_bar["value"] = pct
        self.root.after(0, update)

    def _on_done(self, result):
        self.root.after(0, lambda: self._finish(result))

    def _finish(self, result):
        """v1.0.4 三态诚实收尾。

        result: OriginalsReport（正常结束）/ "cancelled" / False（异常）
        分档规则：
          full    = 全部条目拿到原件（original+image-original，含已存在），
                    无首页预览、无仅文本、无失败
          partial = 有产出但部分条目受服务端限制（预览/仅文本/失败）
          empty   = 一个字节都没拿到（原件/预览/仅文本/已存在全为 0）
        """
        self._set_ui(True)

        if result == "cancelled":
            self._widgets["lbl_progress"].configure(text=s("cancelled"))
            self._progress_bar["value"] = 0
        elif result is False:
            self._widgets["lbl_progress"].configure(text=s("done_fail"))
            self._progress_bar["value"] = 0
        else:
            report = result
            n_failed = len(report.failed)
            if report.downloaded == 0 and report.text_only == 0 and report.skipped == 0:
                state_key = "done_empty"
            elif report.preview == 0 and report.text_only == 0 and n_failed == 0:
                state_key = "done_full"
            else:
                state_key = "done_partial"
            line = report.summary_line()
            self._widgets["lbl_progress"].configure(
                text=f"{s(state_key)} ｜ {line}"
            )
            self._add_log(f"{s(state_key)}")
            self._add_log(f"📊 {line}")
            # v1.0.6: 逐文件字节校验结果 + 校验报告落盘
            self._add_log(s("verify_line", sp=report.size_pass, sf=report.size_fail,
                            po=report.preview_ok, pb=report.preview_bad))
            self._log_coverage(report)
            self._write_report_logged(report)
            self._progress_bar["value"] = 100 if state_key != "done_empty" else 0

    def _log_coverage(self, report):
        """v1.0.7: 内容覆盖统计进日志（回答「文件数对了，内容数对了吗」）。"""
        try:
            for line in report.content_coverage_lines():
                self._add_log(f"   {line}")
        except Exception:
            pass

    def _write_report_logged(self, report):
        """v1.0.7: 统一「写校验报告 + 汇报路径」小助手。"""
        try:
            verify_path = report.write_verify_report()
            if verify_path:
                self._add_log(s("verify_written", path=str(verify_path)))
        except Exception as e:
            self._add_log(f"⚠️ 校验报告写入失败: {e}")

    # ----------------------------------------------------------------
    # ACTIONS
    # ----------------------------------------------------------------
    def _start(self):
        content = self._get_share_text()
        sid = extract_share_id(content)
        if not sid:
            self._widgets["lbl_progress"].configure(text=s("no_share_id"))
            return
        # v1.0.8: 必须先扫码登录（原件地址签发需登录态）
        if not get_session().is_logged_in():
            self._widgets["lbl_progress"].configure(text=s("login_required"))
            messagebox.showinfo(s("btn_login"), s("login_required"))
            return
        save = Path(self._entry_dir.get() or "downloads")
        self._set_ui(False)
        self._widgets["lbl_progress"].configure(text=s("preparing"))
        self._log_widget.configure(state="normal")
        self._log_widget.delete("1.0", END)
        self._log_widget.configure(state="disabled")
        self._task = self._launch_task(sid, save)

    def _launch_task(self, sid, save):
        """v1.0.8: 启动原件直下任务。"""
        task = DownloadTask(sid, save, self._add_log,
                            self._on_progress, self._on_done,
                            multi_thread=self.multi_thread_var.get())
        threading.Thread(target=task.run, daemon=True).start()
        return task

    def _cancel(self):
        if self._task:
            self._task.cancel()
            self._widgets["lbl_progress"].configure(text=s("cancelled"))

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    try:
        ImaDownloaderGUI().run()
    except Exception as e:
        import traceback
        err = traceback.format_exc()
        try:
            messagebox.showerror("IMA Downloader Error", f"启动失败:\n{err}")
        except:
            print("启动失败:", err)
        raise
