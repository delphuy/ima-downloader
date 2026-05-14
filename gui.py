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
from tkinter import Tk, Entry, Button, Label, Frame, END, DISABLED, NORMAL, filedialog, Text
import tkinter.scrolledtext as scrolledtext
from api_service import ImaApiService
from downloader import extract_download_url, sanitize_filename, download_single_file

# ============================================================
# VERSION & UPDATE CONFIG
# ============================================================
__VERSION__ = "1.0.2"
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
    "cancelled":     "⏹ Cancelled",
    "scan_files":    "Scanning knowledge base...",
    "total_files":   "Found {n} files, starting download",
    "existing":      "Already present: {n} files",
    "folder":        "📁 {name}",
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
    "cancelled":     "⏹ 已取消",
    "scan_files":    "📊 扫描知识库...",
    "total_files":   "共 {n} 个文件，开始下载",
    "existing":      "已存在 {n} 个文件",
    "folder":        "📁 {name}",
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
    def __init__(self, share_id, root_dir, on_log, on_progress, on_done):
        self.share_id = share_id
        self.root_dir = root_dir
        self.on_log = on_log
        self.on_progress = on_progress
        self.on_done = on_done
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def is_cancelled(self):
        return self._cancelled

    def run(self):
        try:
            api = ImaApiService()
            self._scan_and_download(api)
            self.on_done(True)
        except Exception as e:
            self.on_log(f"[错误] {e}")
            self.on_done(False)

    def _scan_and_download(self, api):
        # FIX 4: 初始limit从1改为20，与后续分页保持一致，避免分页错位
        resp = api.get_share_info(self.share_id, limit=20, cursor="", folder_id="")
        if resp.code != 0 or not resp.current_path:
            self.on_log("❌ 获取目录失败")
            return
        root_name = sanitize_filename(resp.current_path[0].name)
        root_path = Path(self.root_dir) / root_name
        root_path.mkdir(parents=True, exist_ok=True)
        self.on_log(s("folder", name=root_name))

        existing = {f.name for f in root_path.iterdir() if f.is_file()}
        self.on_log(s("existing", n=len(existing)))

        self.on_log(s("scan_files"))
        all_files = []
        self._collect_files(api, "", all_files)
        self.on_log(s("total_files", n=len(all_files)))

        for i, item in enumerate(all_files, 1):
            if self._cancelled:
                self.on_log(s("cancelled"))
                return
            name = item['name']
            self.on_progress(i, len(all_files), name)
            self._download_one(item, root_path, existing)

        self.on_log(s("done_ok"))

    def _collect_files(self, api, folder_id, result):
        cursor = ""
        while True:
            resp = api.get_share_info(self.share_id, limit=20, cursor=cursor, folder_id=folder_id)
            if resp.code != 0:
                break
            for item in resp.knowledge_list:
                if item.folder_info:
                    self._collect_files(api, item.folder_info.folder_id, result)
                else:
                    url = extract_download_url(item.jump_url)
                    name = sanitize_filename(item.title)
                    if url and name:
                        result.append({'url': url, 'name': name, 'folder_id': folder_id})
            if resp.is_end or not resp.next_cursor:
                break
            cursor = resp.next_cursor

    def _download_one(self, item, root_path, existing):
        name = item['name']
        if name in existing:
            self.on_log(f"[跳过] {name}")
            return
        out = root_path / name
        try:
            download_single_file(item['url'], out, on_log=None)
            self.on_log(f"✅ {name}")
        except Exception as e:
            self.on_log(f"[FAIL] {name} — {e}")


# ============================================================
# GUI
# ============================================================
class ImaDownloaderGUI:
    _lang = "zh"          # default to Chinese
    _root_after = None

    def __init__(self):
        self.root = Tk()
        ImaDownloaderGUI._root_after = self.root.after
        self.root.title("IMA Knowledge Base Downloader")
        self.root.geometry("800x680")
        self.root.configure(bg="#1e1e2e")
        self._task = None
        self._has_placeholder = True
        self._update_dismissed = False
        self._new_ver = None

        # All widgets that need language refresh
        self._widgets = {}

        self._build_ui()
        self._entry_dir.insert(0, str(Path("downloads").resolve()))

        # Show ready silently, start background update check after 5s
        self._widgets["lbl_progress"].configure(text=s("ready"))
        start_update_checker(on_version_found=self._on_version_found)

    # ----------------------------------------------------------------
    # BUILD UI
    # ----------------------------------------------------------------
    def _build_ui(self):
        bg, surface, accent, text, dim, warn = "#1e2e2e", "#2a2a3c", "#7c6af4", "#e8e8f0", "#666688", "#f5c542"

        # ── Update banner (floating at top) ──
        bar = Frame(self.root, bg="#2d2a10", height=40)
        bar.pack(fill="x", padx=12, pady=(8, 0))
        bar.pack_forget()
        bar.columnconfigure(0, weight=1)
        self._update_bar = bar

        self._widgets["lbl_update"] = Label(bar, font=("Microsoft YaHei", 10),
                                             fg=warn, bg="#2d2a10", anchor="w")
        self._widgets["lbl_update"].grid(row=0, column=0, padx=8, pady=6, sticky="ew")

        btn_row = Frame(bar, bg="#2d2a10")
        btn_row.grid(row=0, column=1, padx=(0, 4), pady=4, sticky="ns")

        self._widgets["btn_update"] = Button(btn_row, text=s("btn_update"),
                                             font=("Microsoft YaHei", 9, "bold"),
                                             bg=accent, fg="white", relief="flat",
                                             cursor="hand2", command=self._do_update)
        self._widgets["btn_update"].pack(side="left", padx=2)

        self._widgets["btn_github"] = Button(btn_row, text=s("open_github"),
                                              font=("Microsoft YaHei", 9),
                                              bg="#3d3d5c", fg=text, relief="flat",
                                              cursor="hand2", command=self._open_github)
        self._widgets["btn_github"].pack(side="left", padx=2)

        self._widgets["btn_dismiss"] = Button(btn_row, text=s("update_dismiss"),
                                               font=("Consolas", 9),
                                               bg="#2d2a10", fg=dim, relief="flat",
                                               cursor="hand2", command=self._dismiss_update)
        self._widgets["btn_dismiss"].pack(side="left", padx=2)

        # ── Title bar ──
        top = Frame(self.root, bg=bg)
        top.pack(fill="x", padx=16, pady=(6, 0))
        top.columnconfigure(0, weight=1)

        self._widgets["lbl_title"] = Label(top, text=s("title"),
                                            font=("Microsoft YaHei", 15, "bold"),
                                            fg=accent, bg=bg, anchor="w")
        self._widgets["lbl_title"].grid(row=0, column=0)

        btn_lang = Button(top, text=s("lang_label"),
                          font=("Consolas", 8),
                          bg=bg, fg=dim, relief="flat", bd=0,
                          cursor="hand2", command=self._toggle_lang)
        btn_lang.grid(row=0, column=1, padx=(0, 4))
        self._widgets["btn_lang"] = btn_lang

        btn_check_update = Button(top, text=s("btn_check_update"),
                                  font=("Microsoft YaHei", 9),
                                  bg="#3d3d5c", fg=text, relief="flat",
                                  cursor="hand2", command=self._check_update_manually)
        btn_check_update.grid(row=0, column=2, padx=(0, 4))
        self._widgets["btn_check_update"] = btn_check_update

        # ── Main card ──
        frame = Frame(self.root, bg=surface, padx=16, pady=10)
        frame.pack(fill="x", padx=12, pady=(6, 0))

        Label(frame, text=s("share_label"),
              fg=text, bg=surface).grid(row=0, column=0, sticky="w")

        self._text_share = Text(frame, font=("Microsoft YaHei", 10),
                                bg="#111120", fg=dim,
                                insertbackground=accent,
                                height=5, wrap="word", padx=6, pady=4)
        self._text_share.grid(row=1, column=0, columnspan=2, sticky="ew")
        self._text_share.insert("1.0", s("share_ph"))
        self._text_share.bind("<FocusIn>", self._on_share_focus_in)
        self._text_share.bind("<FocusOut>", self._on_share_focus_out)
        frame.columnconfigure(0, weight=1)

        Label(frame, text=s("dir_label"),
              fg=text, bg=surface).grid(row=2, column=0, sticky="w", pady=(10, 0))

        self._entry_dir = Entry(frame, font=("Consolas", 10), bg="#111120", fg=text)
        self._entry_dir.grid(row=3, column=0, sticky="ew", ipady=4)

        self._widgets["btn_browse"] = Button(frame, text=s("browse"),
                                              command=self._browse, bg="#3d3d5c", fg=text)
        self._widgets["btn_browse"].grid(row=3, column=1, padx=(6, 0))

        btn_frame = Frame(frame, bg=surface)
        btn_frame.grid(row=4, column=0, columnspan=2, pady=(15, 5))

        self._widgets["btn_start"] = Button(btn_frame, text=s("start"),
                                             command=self._start,
                                             bg=accent, fg="white",
                                             font=("Microsoft YaHei", 10, "bold"), padx=20)
        self._widgets["btn_start"].pack(side="left", padx=5)

        self._widgets["btn_cancel"] = Button(btn_frame, text=s("cancel"),
                                              bg="#3d3d5c", fg=text, padx=20)
        self._widgets["btn_cancel"].pack(side="left", padx=5)

        # ── Progress ──
        self._widgets["lbl_progress"] = Label(self.root, text=s("ready"),
                                              font=("Consolas", 12, "bold"),
                                              fg=accent, bg=bg, height=2, anchor="w")
        self._widgets["lbl_progress"].pack(fill="x", padx=16, pady=(8, 4))

        sep = Frame(self.root, bg=accent, height=2)
        sep.pack(fill="x", padx=12)

        # ── Log ──
        self._log_widget = scrolledtext.ScrolledText(
            self.root, font=("Consolas", 9),
            bg="#111120", fg="#d4d4e8", state="disabled",
            wrap="word", padx=10, pady=6, height=4,
        )
        self._log_widget.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self._log_widget.tag_configure("ok", foreground="#6ccf7e")
        self._log_widget.tag_configure("warn", foreground="#f5c542")
        self._log_widget.tag_configure("err", foreground="#f4706c")

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

        # Refresh share text placeholder (keep current content unless it was placeholder)
        was_placeholder = self._has_placeholder
        cur = self._text_share.get("1.0", END).strip()
        self._text_share.delete("1.0", END)
        if was_placeholder or not cur:
            self._text_share.insert("1.0", s("share_ph"))
            self._text_share.configure(fg="#666688")
            self._has_placeholder = True
        else:
            self._text_share.insert("1.0", cur)
            self._text_share.configure(fg="#e8e8f0")
            self._has_placeholder = False

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
            self._text_share.configure(fg="#e8e8f0")
            self._has_placeholder = False

    def _on_share_focus_out(self, _):
        content = self._text_share.get("1.0", END).strip()
        if not content:
            self._text_share.delete("1.0", END)
            self._text_share.insert("1.0", s("share_ph"))
            self._text_share.configure(fg="#666688")
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

    def _add_log(self, msg):
        self._log_widget.configure(state="normal")
        self._log_widget.insert(END, msg + "\n")
        self._log_widget.configure(state="disabled")

    def _on_progress(self, current, total, name):
        self.root.after(0, lambda: self._widgets["lbl_progress"].configure(
            text=f"[{current}/{total}] {name}"))

    def _on_done(self, ok):
        self.root.after(0, lambda: self._finish(ok))

    def _finish(self, ok):
        self._set_ui(True)
        self._widgets["lbl_progress"].configure(text=s("done_ok") if ok else s("done_fail"))

    # ----------------------------------------------------------------
    # ACTIONS
    # ----------------------------------------------------------------
    def _start(self):
        content = self._get_share_text()
        sid = extract_share_id(content)
        if not sid:
            self._widgets["lbl_progress"].configure(text=s("no_share_id"))
            return
        save = Path(self._entry_dir.get() or "downloads")
        self._set_ui(False)
        self._widgets["lbl_progress"].configure(text=s("preparing"))
        self._log_widget.configure(state="normal")
        self._log_widget.delete("1.0", END)
        self._log_widget.configure(state="disabled")

        self._task = DownloadTask(sid, save, self._add_log,
                                  self._on_progress, self._on_done)
        threading.Thread(target=self._task.run, daemon=True).start()

    def _cancel(self):
        if self._task:
            self._task.cancel()
            self._widgets["lbl_progress"].configure(text=s("cancelled"))

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    ImaDownloaderGUI().run()
