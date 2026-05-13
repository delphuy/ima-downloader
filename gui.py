import re
import threading
from pathlib import Path
from tkinter import Tk, Entry, Button, Label, Frame, END, DISABLED, NORMAL, filedialog, Text
import tkinter.scrolledtext as scrolledtext
from api_service import ImaApiService
from downloader import extract_download_url, sanitize_filename, download_single_file

PLACEHOLDER = "找到需要下载的知识库，点击 分享 > 复制链接，将链接粘贴到这里\n例如：\n【ima知识库】行业研究报告库（行研智库） https://ima.qq.com/wiki/?shareId=8ccc0a2d2a8cc1c1dbe68d85576e0274e1c99ed344b167e782e9e15befa574a7"

def extract_share_id(text):
    text = text.strip()
    m = re.search(r'shareId[=:]([a-fA-F0-9]{64})', text)
    if m: return m.group(1)
    if re.fullmatch(r'[a-fA-F0-9]{64}', text): return text
    return ""

class DownloadTask:
    def __init__(self, share_id, root_dir, on_log, on_progress, on_done):
        self.share_id = share_id
        self.root_dir = root_dir
        self.on_log = on_log
        self.on_progress = on_progress
        self.on_done = on_done
        self._cancelled = False
        self._done_count = 0

    def cancel(self): self._cancelled = True
    def is_cancelled(self): return self._cancelled

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
        self.on_log(f"📁 {root_name}")

        existing = {f.name for f in root_path.iterdir() if f.is_file()}
        self.on_log(f"已存在 {len(existing)} 个文件")

        self.on_log("📊 扫描知识库...")
        all_files = []
        self._collect_files(api, "", all_files)
        self.on_log(f"共 {len(all_files)} 个文件，开始下载")

        for i, item in enumerate(all_files, 1):
            if self._cancelled:
                self.on_log("⏹ 已取消")
                return
            name = item['name']
            self.on_progress(i, len(all_files), name)
            self._download_one(item, root_path, existing)

        self.on_log("✅ 全部下载完成")

    def _collect_files(self, api, folder_id, result):
        cursor = ""
        while True:
            resp = api.get_share_info(self.share_id, limit=20, cursor=cursor, folder_id=folder_id)
            if resp.code != 0: break
            for item in resp.knowledge_list:
                if item.folder_info:
                    self._collect_files(api, item.folder_info.folder_id, result)
                else:
                    url = extract_download_url(item.jump_url)
                    name = sanitize_filename(item.title)
                    if url and name:
                        result.append({'url': url, 'name': name, 'folder_id': folder_id})
            if resp.is_end or not resp.next_cursor: break
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

class ImaDownloaderGUI:
    def __init__(self):
        self.root = Tk()
        self.root.title("IMA 知识库下载器")
        self.root.geometry("800x650")
        self.root.configure(bg="#1e1e2e")
        self._task = None
        self._has_placeholder = True
        self._build_ui()
        self._entry_dir.insert(0, str(Path("downloads").resolve()))

    def _build_ui(self):
        bg = "#1e1e2e"
        surface = "#2a2a3c"
        accent = "#7c6af4"
        text = "#e8e8f0"
        dim = "#666688"

        Label(self.root, text="📥 IMA 知识库下载器", font=("Microsoft YaHei", 16, "bold"),
              fg=accent, bg=bg).pack(pady=10)

        frame = Frame(self.root, bg=surface, padx=16, pady=10)
        frame.pack(fill="x", padx=12)

        # 分享链接（多行 Text + placeholder）
        Label(frame, text="分享链接:", fg=text, bg=surface).grid(row=0, column=0, sticky="w")
        self._text_share = Text(frame, font=("Microsoft YaHei", 10),
                                bg="#111120", fg=dim,
                                insertbackground=accent,
                                height=5, wrap="word", padx=6, pady=4)
        self._text_share.grid(row=1, column=0, columnspan=2, sticky="ew")
        self._text_share.insert("1.0", PLACEHOLDER)
        self._text_share.bind("<FocusIn>", self._on_share_focus_in)
        self._text_share.bind("<FocusOut>", self._on_share_focus_out)
        frame.columnconfigure(0, weight=1)

        # 保存目录
        Label(frame, text="保存目录:", fg=text, bg=surface).grid(row=2, column=0, sticky="w", pady=(10,0))
        self._entry_dir = Entry(frame, font=("Consolas", 10), bg="#111120", fg=text)
        self._entry_dir.grid(row=3, column=0, sticky="ew", ipady=4)
        self._btn_browse = Button(frame, text="浏览...", command=self._browse, bg="#3d3d5c", fg=text)
        self._btn_browse.grid(row=3, column=1, padx=(6,0))

        # 按钮区
        btn_frame = Frame(frame, bg=surface)
        btn_frame.grid(row=4, column=0, columnspan=2, pady=(15,5))
        self._btn_start = Button(btn_frame, text="▶ 开始下载", command=self._start,
                                 bg=accent, fg="white", font=("Microsoft YaHei", 10, "bold"), padx=20)
        self._btn_start.pack(side="left", padx=5)
        self._btn_cancel = Button(btn_frame, text="⏹ 取消", command=self._cancel,
                                  bg="#3d3d5c", fg=text, padx=20)
        self._btn_cancel.pack(side="left", padx=5)

        # 进度区
        self._lbl_progress = Label(self.root, text="就绪", font=("Consolas", 12, "bold"),
                                   fg=accent, bg=bg, height=2, anchor="w")
        self._lbl_progress.pack(fill="x", padx=16, pady=(8, 4))

        sep = Frame(self.root, bg=accent, height=2)
        sep.pack(fill="x", padx=12)

        # 日志区（固定高度，不自动滚动）
        self._log_widget = scrolledtext.ScrolledText(
            self.root, font=("Consolas", 9),
            bg="#111120", fg="#d4d4e8", state="disabled",
            wrap="word", padx=10, pady=6,
            height=4,
        )
        self._log_widget.pack(fill="both", expand=True, padx=12, pady=(0,12))
        self._log_widget.tag_configure("ok", foreground="#6ccf7e")
        self._log_widget.tag_configure("warn", foreground="#f5c542")
        self._log_widget.tag_configure("err", foreground="#f4706c")

    def _on_share_focus_in(self, event):
        if self._has_placeholder:
            self._text_share.delete("1.0", "end-1c")
            self._text_share.configure(fg="#e8e8f0")
            self._has_placeholder = False

    def _on_share_focus_out(self, event):
        content = self._text_share.get("1.0", "end-1c").strip()
        if not content:
            self._text_share.insert("1.0", PLACEHOLDER)
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
        s = NORMAL if enabled else DISABLED
        self._text_share.configure(state=s)
        self._entry_dir.configure(state=s)
        self._btn_browse.configure(state=s)
        self._btn_start.configure(state=s)

    def _add_log(self, msg):
        self._log_widget.configure(state="normal")
        self._log_widget.insert(END, msg + "\n")
        # 不调用 see(END)，日志不自动滚到底部
        self._log_widget.configure(state="disabled")

    def _on_progress(self, current, total, name):
        self.root.after(0, lambda: self._lbl_progress.configure(
            text=f"[{current}/{total}] {name}"
        ))

    def _on_done(self, ok):
        self.root.after(0, lambda: self._finish(ok))

    def _finish(self, ok):
        self._set_ui(True)
        self._lbl_progress.configure(text="✅ 完成" if ok else "❌ 失败")

    def _start(self):
        content = self._get_share_text()
        sid = extract_share_id(content)
        if not sid:
            self._lbl_progress.configure(text="❌ 无法提取 share_id，请检查链接")
            return
        save = Path(self._entry_dir.get() or "downloads")
        self._set_ui(False)
        self._lbl_progress.configure(text="准备中...")
        self._log_widget.configure(state="normal")
        self._log_widget.delete("1.0", END)
        self._log_widget.configure(state="disabled")

        self._task = DownloadTask(sid, save, self._add_log, self._on_progress, self._on_done)
        threading.Thread(target=self._task.run, daemon=True).start()

    def _cancel(self):
        if self._task:
            self._task.cancel()
            self._lbl_progress.configure(text="⏹ 取消中...")

    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    ImaDownloaderGUI().run()
