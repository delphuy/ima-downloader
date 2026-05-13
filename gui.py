import re
import threading
import urllib.request
import json
import os
import sys
import tempfile
import shutil
from pathlib import Path
from tkinter import Tk, Entry, Button, Label, Frame, END, DISABLED, NORMAL, filedialog, Text
import tkinter.scrolledtext as scrolledtext
from api_service import ImaApiService
from downloader import extract_download_url, sanitize_filename, download_single_file

# ============================================================
# VERSION & UPDATE CONFIG
# ============================================================
__VERSION__ = "1.0.0"
UPDATE_API = "https://api.github.com/repos/delphuy/ima-downloader/releases/latest"
DOWNLOAD_URL = "https://github.com/delphuy/ima-downloader/releases/latest"

# ============================================================
# STRINGS (English / Chinese)
# ============================================================
LANG = {}

LANG["en"] = {
    "title":         "📥 IMA Knowledge Base Downloader",
    "share_label":   "Share Link:",
    "share_ph":      "Open the IMA Knowledge Base, click Share → Copy Link, paste it here\nExample:\n【ima knowledge】Industry Research Report Library https://ima.qq.com/wiki/?shareId=8ccc0a2d2a8cc1c1dbe68d85576e0274e1c99ed344b167e782e9e15befa574a7",
    "dir_label":     "Save Folder:",
    "browse":       "Browse...",
    "start":         "▶ Start Download",
    "cancel":        "⏹ Cancel",
    "ready":         "Ready — paste a share link to begin",
    "preparing":     "Preparing...",
    "update_avail":  "🆕 Update available: v{new_ver} — click to download",
    "no_update":     "已是最新版本 v{ver}",
    "check_update":  "Checking for updates...",
    "update_fail":   "Update check timed out",
    "no_share_id":   "Cannot extract share_id — check the link",
    "downloading":   "Downloading...",
    "done_ok":       "✅ Download complete",
    "done_fail":     "❌ Download failed",
    "cancelled":     "⏹ Cancelled",
    "scan_files":    "Scanning knowledge base...",
    "total_files":   "Found {n} files, starting download",
    "existing":      "Already present: {n} files",
    "folder":        "📁 {name}",
    "update_dismiss": "✕",
    "lang_label":    "EN | 中文",
}

LANG["zh"] = {
    "title":         "📥 IMA 知识库下载器",
    "share_label":   "分享链接:",
    "share_ph":      "找到需要下载的知识库，点击 分享 > 复制链接，将链接粘贴到这里\n例如：\n【ima知识库】行业研究报告库（行研智库） https://ima.qq.com/wiki/?shareId=8ccc0a2d2a8cc1c1dbe68d85576e0274e1c99ed344b167e782e9e15befa574a7",
    "dir_label":     "保存目录:",
    "browse":       "浏览...",
    "start":         "▶ 开始下载",
    "cancel":        "⏹ 取消",
    "ready":         "就绪 — 粘贴分享链接即可开始",
    "preparing":     "准备中...",
    "update_avail":  "🆕 发现新版本 v{new_ver} — 点击下载更新",
    "no_update":     "已是最新版本 v{ver}",
    "check_update":  "检查更新中...",
    "update_fail":   "更新检查超时",
    "no_share_id":   "❌ 无法提取 share_id，请检查链接",
    "downloading":   "下载中...",
    "done_ok":       "✅ 全部下载完成",
    "done_fail":     "❌ 下载失败",
    "cancelled":     "⏹ 已取消",
    "scan_files":    "📊 扫描知识库...",
    "total_files":   "共 {n} 个文件，开始下载",
    "existing":      "已存在 {n} 个文件",
    "folder":        "📁 {name}",
    "update_dismiss": "✕",
    "lang_label":    "EN | 中文",
}


def s(key, **kw):
    return LANG[ImaDownloaderGUI._lang][key].format(**kw)


# ============================================================
# VERSION CHECKER (runs in background thread, 3s timeout)
# ============================================================
def check_version(callback):
    """Fetch latest release tag from GitHub. Calls callback(new_ver_str or None) on main thread."""
    def worker():
        new_ver = None
        try:
            req = urllib.request.Request(UPDATE_API, headers={"Accept": "application/vnd.github.v3+json"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read())
                tag = data.get("tag_name", "")
                # strip leading 'v' if present
                new_ver = tag.lstrip("v")
        except Exception:
            pass  # silently skip on any error / timeout
        def _notify():
            callback(new_ver)
        ImaDownloaderGUI._root_after(_notify)
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
        self._done_count = 0

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
        resp = api.get_share_info(self.share_id, limit=1, cursor="", folder_id="")
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
            self._done_count += 1
            self.on_log(f"[跳过] {name}")
            return
        out = root_path / name
        try:
            download_single_file(item['url'], out, on_log=None)
            self._done_count += 1
            self.on_log(f"✅ {name}")
        except Exception as e:
            self.on_log(f"[FAIL] {name} — {e}")


# ============================================================
# GUI
# ============================================================
class ImaDownloaderGUI:
    _lang = "zh"   # default: Chinese
    _root_after = None  # set in __init__

    def __init__(self):
        self.root = Tk()
        ImaDownloaderGUI._root_after = self.root.after
        self.root.title("IMA 知识库下载器")
        self.root.geometry("800x680")
        self.root.configure(bg="#1e1e2e")
        self._task = None
        self._has_placeholder = True
        self._update_shown = False

        self._update_bar = None   # update banner frame
        self._update_dismissed = False

        self._build_ui()
        self._entry_dir.insert(0, str(Path("downloads").resolve()))

        # Start version check in background
        self._lbl_progress.configure(text=s("check_update"))
        check_version(self._on_version_checked)

    # ----------------------------------------------------------------
    # UI BUILD
    # ----------------------------------------------------------------
    def _build_ui(self):
        bg = "#1e1e2e"
        surface = "#2a2a3c"
        accent = "#7c6af4"
        text = "#e8e8f0"
        dim = "#666688"
        warn = "#f5c542"

        # ---- Top bar: title + lang toggle ----
        top = Frame(self.root, bg=bg)
        top.pack(fill="x", padx=16, pady=(8, 0))
        top.columnconfigure(0, weight=1)

        lbl_title = Label(top, text=s("title"),
                          font=("Microsoft YaHei", 15, "bold"),
                          fg=accent, bg=bg, anchor="w")
        lbl_title.grid(row=0, column=0)

        btn_lang = Button(top, text=s("lang_label"),
                          font=("Consolas", 8),
                          bg=bg, fg=dim, relief="flat", bd=0,
                          cursor="hand2", command=self._toggle_lang)
        btn_lang.grid(row=0, column=1, padx=(0, 4))

        # ---- Update banner (hidden by default) ----
        self._update_bar = Frame(self.root, bg="#2d2a10", height=36)
        self._update_bar.pack(fill="x", padx=12, pady=(6, 0))
        self._update_bar.pack_forget()
        self._update_bar.columnconfigure(0, weight=1)

        self._lbl_update = Label(self._update_bar,
                                 font=("Microsoft YaHei", 10),
                                 fg=warn, bg="#2d2a10", anchor="w")
        self._lbl_update.grid(row=0, column=0, padx=8, pady=4, sticky="w")

        self._btn_update = Button(self._update_bar, text="⬇ 下载",
                                 font=("Microsoft YaHei", 9, "bold"),
                                 bg=accent, fg="white", relief="flat",
                                 cursor="hand2", command=self._do_update)
        self._btn_update.grid(row=0, column=1, padx=(0, 6), pady=4)

        self._btn_dismiss = Button(self._update_bar, text=s("update_dismiss"),
                                    font=("Consolas", 9),
                                    bg="#2d2a10", fg=dim, relief="flat",
                                    cursor="hand2", command=self._dismiss_update)
        self._btn_dismiss.grid(row=0, column=2, padx=(0, 6), pady=4)

        # ---- Main card ----
        frame = Frame(self.root, bg=surface, padx=16, pady=10)
        frame.pack(fill="x", padx=12, pady=(6, 0))

        Label(frame, text=s("share_label"),
              fg=text, bg=surface).grid(row=0, column=0, sticky="w")

        ph_text = s("share_ph")
        self._text_share = Text(frame, font=("Microsoft YaHei", 10),
                                bg="#111120", fg=dim,
                                insertbackground=accent,
                                height=5, wrap="word", padx=6, pady=4)
        self._text_share.grid(row=1, column=0, columnspan=2, sticky="ew")
        self._text_share.insert("1.0", ph_text)
        self._text_share.bind("<FocusIn>", self._on_share_focus_in)
        self._text_share.bind("<FocusOut>", self._on_share_focus_out)
        frame.columnconfigure(0, weight=1)

        Label(frame, text=s("dir_label"),
              fg=text, bg=surface).grid(row=2, column=0, sticky="w", pady=(10, 0))
        self._entry_dir = Entry(frame, font=("Consolas", 10), bg="#111120", fg=text)
        self._entry_dir.grid(row=3, column=0, sticky="ew", ipady=4)
        self._btn_browse = Button(frame, text=s("browse"),
                                  command=self._browse, bg="#3d3d5c", fg=text)
        self._btn_browse.grid(row=3, column=1, padx=(6, 0))

        btn_frame = Frame(frame, bg=surface)
        btn_frame.grid(row=4, column=0, columnspan=2, pady=(15, 5))
        self._btn_start = Button(btn_frame, text=s("start"),
                                  command=self._start,
                                  bg=accent, fg="white",
                                  font=("Microsoft YaHei", 10, "bold"), padx=20)
        self._btn_start.pack(side="left", padx=5)
        self._btn_cancel = Button(btn_frame, text=s("cancel"),
                                   bg="#3d3d5c", fg=text, padx=20)
        self._btn_cancel.pack(side="left", padx=5)

        # ---- Progress ----
        self._lbl_progress = Label(self.root, text=s("ready"),
                                   font=("Consolas", 12, "bold"),
                                   fg=accent, bg=bg, height=2, anchor="w")
        self._lbl_progress.pack(fill="x", padx=16, pady=(8, 4))

        sep = Frame(self.root, bg=accent, height=2)
        sep.pack(fill="x", padx=12)

        # ---- Log ----
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
    # LANGUAGE SWITCH
    # ----------------------------------------------------------------
    def _toggle_lang(self):
        ImaDownloaderGUI._lang = "en" if self._lang == "zh" else "zh"
        self._refresh_labels()

    def _refresh_labels(self):
        """Rebuild key label texts after language change."""
        try:
            self.root.title(LANG[self._lang]["title"].replace("📥 ", ""))
            self._lbl_progress.configure(text=s("ready"))
        except Exception:
            pass

    # ----------------------------------------------------------------
    # UPDATE CHECK
    # ----------------------------------------------------------------
    def _on_version_checked(self, new_ver):
        """Called from main thread after background version check."""
        if new_ver and self._compare_ver(new_ver):
            self._show_update_bar(new_ver)
        else:
            self._lbl_progress.configure(text=s("no_update", ver=__VERSION__))

    def _compare_ver(self, new_ver):
        """Return True if new_ver > current version."""
        def v(vstr):
            return [int(x) for x in vstr.split(".") if x.isdigit()]
        try:
            nv = v(new_ver)
            cv = v(__VERSION__)
            for a, b in zip(nv, cv):
                if a > b:
                    return True
                if a < b:
                    return False
            return len(nv) > len(cv)
        except Exception:
            return False

    def _show_update_bar(self, new_ver):
        self._lbl_update.configure(text=s("update_avail", new_ver=new_ver))
        self._update_bar.pack(fill="x", padx=12, pady=(6, 0))
        if not self._update_shown:
            self._update_shown = True
            if not self._update_dismissed:
                self._lbl_progress.configure(
                    text=s("update_avail", new_ver=new_ver))

    def _dismiss_update(self):
        self._update_dismissed = True
        self._update_bar.pack_forget()

    def _do_update(self):
        import webbrowser
        webbrowser.open(DOWNLOAD_URL)

    # ----------------------------------------------------------------
    # INPUT HELPERS
    # ----------------------------------------------------------------
    def _on_share_focus_in(self, _):
        if self._has_placeholder:
            self._text_share.delete("1.0", "end-1c")
            self._text_share.configure(fg="#e8e8f0")
            self._has_placeholder = False

    def _on_share_focus_out(self, _):
        content = self._text_share.get("1.0", "end-1c").strip()
        if not content:
            ph_text = s("share_ph")
            self._text_share.insert("1.0", ph_text)
            self._text_share.configure(fg="#666688")
            self._has_placeholder = True

    def _get_share_text(self):
        if self._has_placeholder:
            return ""
        return self._text_share.get("1.0", "end-1c").strip()

    def _browse(self):
        p = filedialog.askdirectory()
        if p:
            self._entry_dir.delete(0, END)
            self._entry_dir.insert(0, p)

    def _set_ui(self, enabled):
        s_state = NORMAL if enabled else DISABLED
        self._text_share.configure(state=s_state)
        self._entry_dir.configure(state=s_state)
        self._btn_browse.configure(state=s_state)
        self._btn_start.configure(state=s_state)

    def _add_log(self, msg):
        self._log_widget.configure(state="normal")
        self._log_widget.insert(END, msg + "\n")
        self._log_widget.configure(state="disabled")

    def _on_progress(self, current, total, name):
        self.root.after(0, lambda: self._lbl_progress.configure(
            text=f"[{current}/{total}] {name}"
        ))

    def _on_done(self, ok):
        self.root.after(0, lambda: self._finish(ok))

    def _finish(self, ok):
        self._set_ui(True)
        self._lbl_progress.configure(
            text=s("done_ok") if ok else s("done_fail"))

    # ----------------------------------------------------------------
    # ACTIONS
    # ----------------------------------------------------------------
    def _start(self):
        content = self._get_share_text()
        sid = extract_share_id(content)
        if not sid:
            self._lbl_progress.configure(text=s("no_share_id"))
            return
        save = Path(self._entry_dir.get() or "downloads")
        self._set_ui(False)
        self._lbl_progress.configure(text=s("preparing"))
        self._log_widget.configure(state="normal")
        self._log_widget.delete("1.0", END)
        self._log_widget.configure(state="disabled")

        self._task = DownloadTask(sid, save, self._add_log,
                                  self._on_progress, self._on_done)
        threading.Thread(target=self._task.run, daemon=True).start()

    def _cancel(self):
        if self._task:
            self._task.cancel()
            self._lbl_progress.configure(text=s("cancelled"))

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    ImaDownloaderGUI().run()