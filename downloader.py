# downloader.py - 文件下载器
# 对应 Java 版本的 FileDownloader.java + KnowledgeProcessor.java

import os
import re
import shutil
import subprocess
import requests
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Callable, Optional, Set
from urllib.parse import urlparse
import mimetypes

from models import KnowledgeItem, FailedDownload, KnowledgeFile, MediaTypeInfo


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


# ── 文件名 / 文件夹名清理（统一规则）─────────────────────────────

def sanitize_name(name: str) -> str:
    """清理文件或文件夹名称，移除非法字符。文件和文件夹共用同一规则。"""
    if not name:
        return "unknown_file"
    return re.sub(r'[\\/:*?"<>|]', "_", name).strip()


# 向后兼容别名（旧代码仍可使用 sanitize_filename）
sanitize_filename = sanitize_name


# ── 扩展名推断（修复无扩展名文件问题）───────────────────────────

def build_safe_filename(
    title: str,
    item: Optional[KnowledgeItem] = None,
    download_url: str = "",
) -> str:
    """根据 title、media_type_info 和 download_url 构建带合理扩展名的安全文件名。

    优先级：
    1. 如果 title 本身已有扩展名，保留。
    2. 根据 media_type_info.name 推断（PDF / Word / 链接 等）。
    3. 从 download_url 路径提取扩展名。
    4. 链接类用 .url（可直接点击），其他用 .html 。
    """
    safe = sanitize_name(title or "untitled")

    # 1. title 本身已经有扩展名
    base, ext = os.path.splitext(safe)
    if ext and len(ext) > 1:
        return safe

    ext = ""

    # 2. 从 media_type_info 推断
    if item and item.media_type_info and item.media_type_info.name:
        mname = item.media_type_info.name.lower()
        type_map = {
            "pdf": ".pdf",
            "word": ".docx", "doc": ".docx",
            "excel": ".xlsx", "xls": ".xlsx",
            "ppt": ".pptx", "powerpoint": ".pptx",
            "markdown": ".md", "md": ".md",
            "image": ".png", "图片": ".png",
            "video": ".mp4",
            "link": ".url", "链接": ".url", "url": ".url", "外部": ".url", "网页": ".html", "web": ".html",
            "text": ".md", "文章": ".md", "内容": ".md",
        }
        for key, val in type_map.items():
            if key in mname:
                ext = val
                break

    # 3. 从下载 URL 尝试提取
    if not ext and download_url:
        try:
            p = urlparse(download_url)
            _, url_ext = os.path.splitext(p.path)
            if url_ext and len(url_ext) > 1:
                ext = url_ext
        except Exception:
            pass

    if ext:
        if not safe.lower().endswith(ext.lower()):
            return safe + ext
        return safe

    # 4. 默认回退（链接已在 type_map 中处理为 .url）
    return safe + ".html"


def get_content_type(title: str, media_type_info: Optional["MediaTypeInfo"] = None) -> str:
    """根据 media_type_info 或 title 判断内容来源类型，用于多线程分组。"""
    if media_type_info and media_type_info.name:
        mname = media_type_info.name.lower()
        if any(k in mname for k in ["链接", "link", "url", "外部", "网页"]):
            return "链接类型"
        if any(k in mname for k in ["pdf", "word", "excel", "ppt", "powerpoint", "image", "图片", "video"]):
            return "文档类型"
        if any(k in mname for k in ["markdown", "md", "text", "文章", "内容"]):
            return "文章类型"

    # fallback from title/filename
    t = (title or "").lower()
    if any(k in t for k in ["链接", "link", "url"]):
        return "链接类型"
    if any(k in t for k in [".pdf", ".doc", ".ppt", ".xls", "报告", "白皮书"]):
        return "文档类型"
    return "文章类型"


def ensure_extension_from_response(target_path: Path, resp: "requests.Response") -> Path:
    """下载后根据响应头修正扩展名（作为第二道保险）。"""
    if target_path.suffix:
        return target_path

    # Content-Disposition
    disp = resp.headers.get("Content-Disposition", "") or ""
    if "filename" in disp.lower():
        m = re.search(r'filename\*?=(?:UTF-8\'\')?["\']?([^"\';]+)', disp, re.I)
        if m:
            suggested = sanitize_name(m.group(1))
            if os.path.splitext(suggested)[1]:
                return target_path.with_name(suggested)

    # Content-Type
    ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip()
    if ctype:
        guessed = mimetypes.guess_extension(ctype)
        if guessed:
            return target_path.with_suffix(guessed)

    # 默认 .html 更安全
    return target_path.with_suffix(".html")


def _looks_like_verification_page(path: Path) -> bool:
    """检测是否是微信/IMA的验证页或环境异常页。"""
    try:
        if not path.exists() or path.stat().st_size > 8192:
            return False
        content = path.read_bytes().decode("utf-8", errors="ignore").lower()
        bad_keywords = [
            "环境异常", "去验证", "完成验证", "当前环境异常",
            "微信公众平台", "environment exception", "验证后即可继续访问"
        ]
        return any(kw in content for kw in bad_keywords)
    except Exception:
        return False



# ── 单文件下载（支持回调日志）──────────────────────────────────

def download_single_file(
    url: str,
    output_path: Path,
    timeout: tuple = (15, 180),
    on_log: Optional[Callable[[str], None]] = None,
) -> None:
    """下载单个文件，失败抛出 IOError。

    会根据响应头尝试修正扩展名（解决部分内容无扩展名的问题）。
    """
    _log = on_log or print
    _log(f"[DOWNLOADING] -> {output_path.name}")

    headers = _download_headers()
    with requests.get(url, headers=headers, stream=True, timeout=timeout, allow_redirects=True) as resp:
        resp.raise_for_status()
        total_size = int(resp.headers.get("Content-Length", 0))

        # 第二道保险：根据响应头修正扩展名
        final_path = ensure_extension_from_response(output_path, resp)

        final_path.parent.mkdir(parents=True, exist_ok=True)
        with final_path.open("wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        if final_path != output_path:
            _log(f"[RENAMED] {output_path.name} -> {final_path.name}")

        # 检测是否下载到验证页（常见于微信链接/外部内容）
        if _looks_like_verification_page(final_path):
            _log(f"[WARNING] 内容为验证页面（环境异常），无法获取真实文档")
            url_file = final_path.with_suffix(".url")
            try:
                with url_file.open("w", encoding="utf-8") as f:
                    f.write("[InternetShortcut]\n")
                    f.write(f"URL={url}\n")
                final_path.unlink(missing_ok=True)
                final_path = url_file
                _log(f"[LINK] 已转为可点击链接文件: {final_path.name}")
            except Exception as e:
                _log(f"[WARN] 转换失败: {e}")

        _log(f"[DONE] {final_path.name} ({_format_size(total_size)})")


def _format_size(size: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"


def _download_headers(referer: str = "https://ima.qq.com/") -> dict:
    """更真实的浏览器请求头，减少被识别为机器人导致返回验证页。"""
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": referer,
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }


# ── 使用浏览器打印网页为 PDF（针对链接/URL类型内容）────────────────

def find_browser_executable() -> Optional[str]:
    """查找 Chrome 或 Edge 可执行文件路径（Windows 优先）。"""
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p

    # 尝试 PATH
    for name in ["chrome", "msedge", "google-chrome", "chromium"]:
        found = shutil.which(name)
        if found:
            return found
    return None


def print_url_to_pdf(url: str, output_pdf: Path, timeout: int = 90) -> bool:
    """
    使用 Chrome/Edge headless 模式将网页“打印”为 PDF。
    类似浏览器 Ctrl+P → 另存为 PDF 的效果，能较好渲染 JS/CSS。
    返回是否成功。
    """
    browser = find_browser_executable()
    if not browser:
        return False

    output_pdf = Path(output_pdf).with_suffix(".pdf")
    output_pdf.parent.mkdir(parents=True, exist_ok=True)

    # 常见 headless print 参数
    cmd = [
        browser,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-extensions",
        "--disable-background-networking",
        "--window-position=-32000,-32000",
        "--window-size=1,1",
        f"--print-to-pdf={str(output_pdf)}",
        "--print-to-pdf-no-header",
        "--no-pdf-header-footer",
        url,
    ]

    try:
        startupinfo = None
        creationflags = 0
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            creationflags = subprocess.CREATE_NO_WINDOW

        result = subprocess.run(
            cmd,
            timeout=timeout,
            capture_output=True,
            text=True,
            startupinfo=startupinfo,
            creationflags=creationflags,
        )
        success = (
            result.returncode == 0
            and output_pdf.exists()
            and output_pdf.stat().st_size > 2048  # 太小可能是失败页
        )
        return success
    except subprocess.TimeoutExpired:
        return False
    except Exception:
        return False


# ── FileDownloader 类 ───────────────────────────────────────────

class FileDownloader:
    """并发下载文件，管理失败任务。"""

    def __init__(self, max_workers: int = 20, timeout: tuple = (15, 180), max_category_workers: int = 6):
        self.max_workers = max_workers
        self.timeout = timeout
        self.max_category_workers = max_category_workers
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
        enable_print_pdf: bool = True,
    ) -> List[FailedDownload]:
        failed: List[FailedDownload] = []
        directory.mkdir(parents=True, exist_ok=True)

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {}
            for item in items:
                url = extract_download_url(item.jump_url)
                safe_name = build_safe_filename(item.title, item=item, download_url=url)
                if not url or not safe_name:
                    continue
                out_path = directory / safe_name

                # 链接 / URL 类型：受 enable_print_pdf 控制
                if safe_name.lower().endswith(('.url', '.html')) or any(k in safe_name.lower() for k in ['链接', 'link', 'url']):
                    pdf_path = out_path.with_suffix(".pdf")
                    if pdf_path.exists() or out_path.exists():
                        self._log(f"[SKIP] {safe_name}")
                    else:
                        if enable_print_pdf:
                            if print_url_to_pdf(url, pdf_path):
                                self._log(f"[PDF] {safe_name} （浏览器打印生成PDF）")
                                continue
                            else:
                                url_file = out_path.with_suffix(".url")
                                url_file.parent.mkdir(parents=True, exist_ok=True)
                                with url_file.open("w", encoding="utf-8") as f:
                                    f.write("[InternetShortcut]\n")
                                    f.write(f"URL={url}\n")
                                self._log(f"[LINK] {safe_name} （打印失败，已保存为链接）")
                        else:
                            url_file = out_path.with_suffix(".url")
                            url_file.parent.mkdir(parents=True, exist_ok=True)
                            with url_file.open("w", encoding="utf-8") as f:
                                f.write("[InternetShortcut]\n")
                                f.write(f"URL={url}\n")
                            self._log(f"[LINK] {safe_name} （已保存为链接，未打印PDF）")
                    continue

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
        headers = _download_headers()
        with requests.get(url, headers=headers, stream=True, timeout=self.timeout, allow_redirects=True) as resp:
            resp.raise_for_status()
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with out_path.open("wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

        final = out_path
        if _looks_like_verification_page(out_path):
            self._log(f"[WARNING] 内容为验证页面（环境异常），无法获取真实文档")
            url_file = out_path.with_suffix(".url")
            try:
                with url_file.open("w", encoding="utf-8") as f:
                    f.write("[InternetShortcut]\n")
                    f.write(f"URL={url}\n")
                out_path.unlink(missing_ok=True)
                final = url_file
                self._log(f"[LINK] 已转为可点击链接文件: {final.name}")
            except Exception as e:
                self._log(f"[WARN] 转换失败: {e}")

        self._log(f"[DONE] {final.name}")

    def download_knowledge_files(
        self,
        files: List[KnowledgeFile],
        base_dir: Path,
        on_progress: Optional[Callable[[int, int, str], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
        existing_rels: Optional[Set[str]] = None,
        enable_print_pdf: bool = True,
    ) -> List[FailedDownload]:
        """新统一接口：按 KnowledgeFile.rel_path 存放文件，正确重建目录结构。

        支持：
        - 相对路径 exists 跳过（existing_rels 推荐使用 rglob 预计算）
        - cancel_check
        - on_progress(current, total, rel_str)
        - 自动为每个文件 mkdir parents
        """
        failed: List[FailedDownload] = []
        base_dir.mkdir(parents=True, exist_ok=True)

        if existing_rels is None:
            existing_rels = set()

        total = len(files)
        processed = 0

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {}
            for kf in files:
                if cancel_check and cancel_check():
                    break
                if not kf.url or not str(kf.rel_path):
                    continue

                out_path = base_dir / kf.rel_path
                rel_str = kf.rel_path.as_posix()  # 跨平台一致的相对路径字符串（使用 /）

                # 链接 / URL 类型内容：受 enable_print_pdf 控制
                is_link_type = str(kf.rel_path).lower().endswith(('.url', '.html'))
                if is_link_type or (kf.title and any(k in kf.title.lower() for k in ['链接', 'link', 'url'])):
                    if rel_str in existing_rels or (out_path.with_suffix('.pdf').exists() or out_path.exists()):
                        self._log(f"[SKIP] {rel_str}")
                    else:
                        if enable_print_pdf:
                            pdf_path = out_path.with_suffix(".pdf")
                            if print_url_to_pdf(kf.url, pdf_path):
                                self._log(f"[PDF] {rel_str} （浏览器打印生成PDF）")
                                processed += 1
                                if on_progress:
                                    on_progress(processed, total, str(pdf_path.relative_to(base_dir)))
                                continue
                            else:
                                url_file = out_path.with_suffix(".url")
                                url_file.parent.mkdir(parents=True, exist_ok=True)
                                with url_file.open("w", encoding="utf-8") as f:
                                    f.write("[InternetShortcut]\n")
                                    f.write(f"URL={kf.url}\n")
                                self._log(f"[LINK] {rel_str} （打印失败，已保存为链接）")
                        else:
                            url_file = out_path.with_suffix(".url")
                            url_file.parent.mkdir(parents=True, exist_ok=True)
                            with url_file.open("w", encoding="utf-8") as f:
                                f.write("[InternetShortcut]\n")
                                f.write(f"URL={kf.url}\n")
                            self._log(f"[LINK] {rel_str} （已保存为链接，未打印PDF）")
                    processed += 1
                    if on_progress:
                        on_progress(processed, total, rel_str)
                    continue

                if rel_str in existing_rels or out_path.exists():
                    self._log(f"[SKIP] {rel_str}")
                    processed += 1
                    if on_progress:
                        on_progress(processed, total, rel_str)
                    continue

                out_path.parent.mkdir(parents=True, exist_ok=True)
                fut = executor.submit(self._download_task, kf.url, out_path, rel_str)
                futures[fut] = (kf.url, out_path, rel_str)

            for fut in as_completed(futures):
                url, out_path, rel_str = futures[fut]
                exc = fut.exception()
                processed += 1
                if exc:
                    self._log(f"[FAIL] {rel_str} | {exc}")
                    failed.append(FailedDownload(download_url=url, output_path=out_path))
                elif on_progress:
                    on_progress(processed, total, rel_str)

        return failed

    def download_grouped_files(
        self,
        grouped: dict[str, List[KnowledgeFile]],
        base_dir: Path,
        on_progress: Optional[Callable[[int, int, str], None]] = None,
        on_category_progress: Optional[Callable[[str, int, int, str], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
        existing_rels: Optional[Set[str]] = None,
        enable_print_pdf: bool = True,
    ) -> List[FailedDownload]:
        """
        按内容类型分组下载（链接类型/文档类型/文章类型）。
        - 不同类型使用并行线程（最多 self.max_category_workers）
        - 同一类型的文件在同一个线程内顺序下载
        返回失败列表。
        """
        failed: List[FailedDownload] = []
        base_dir.mkdir(parents=True, exist_ok=True)

        if existing_rels is None:
            existing_rels = set()

        categories = list(grouped.keys())
        total_files = sum(len(fs) for fs in grouped.values())
        global_processed = 0

        def _download_one_category(cat_name: str, files: List[KnowledgeFile]):
            nonlocal global_processed
            cat_total = len(files)
            cat_processed = 0

            self._log(f"📁 开始类型: {cat_name} ({cat_total} 个文件)")

            for kf in files:
                if cancel_check and cancel_check():
                    return

                if not kf.url or not str(kf.rel_path):
                    continue

                out_path = base_dir / kf.rel_path
                rel_str = kf.rel_path.as_posix()

                if rel_str in existing_rels or out_path.exists():
                    self._log(f"[SKIP] {rel_str}")
                    cat_processed += 1
                    global_processed += 1
                    if on_progress:
                        on_progress(global_processed, total_files, rel_str)
                    if on_category_progress:
                        on_category_progress(cat_name, cat_processed, cat_total, rel_str)
                    continue

                # 链接特殊处理（受 print_pdf 勾选控制）
                is_link = str(kf.rel_path).lower().endswith(('.url', '.html')) or (kf.title and any(k in kf.title.lower() for k in ['链接', 'link', 'url']))
                if is_link:
                    if rel_str in existing_rels or (out_path.with_suffix('.pdf').exists() or out_path.exists()):
                        self._log(f"[SKIP] {rel_str}")
                    else:
                        if enable_print_pdf:
                            pdf_path = out_path.with_suffix(".pdf")
                            if print_url_to_pdf(kf.url, pdf_path):
                                self._log(f"[PDF] {rel_str} （浏览器打印生成PDF）")
                            else:
                                url_file = out_path.with_suffix(".url")
                                url_file.parent.mkdir(parents=True, exist_ok=True)
                                with url_file.open("w", encoding="utf-8") as f:
                                    f.write("[InternetShortcut]\n")
                                    f.write(f"URL={kf.url}\n")
                                self._log(f"[LINK] {rel_str} （打印失败，已保存为链接）")
                        else:
                            url_file = out_path.with_suffix(".url")
                            url_file.parent.mkdir(parents=True, exist_ok=True)
                            with url_file.open("w", encoding="utf-8") as f:
                                f.write("[InternetShortcut]\n")
                                f.write(f"URL={kf.url}\n")
                            self._log(f"[LINK] {rel_str} （已保存为链接，未打印PDF）")
                    cat_processed += 1
                    global_processed += 1
                    if on_progress:
                        on_progress(global_processed, total_files, rel_str)
                    if on_category_progress:
                        on_category_progress(cat_name, cat_processed, cat_total, rel_str)
                    continue

                try:
                    download_single_file(kf.url, out_path, timeout=self.timeout, on_log=self._log)
                    self._log(f"✅ {rel_str}")
                except Exception as e:
                    self._log(f"[FAIL] {rel_str} — {e}")
                    failed.append(FailedDownload(download_url=kf.url, output_path=out_path))

                cat_processed += 1
                global_processed += 1
                if on_progress:
                    on_progress(global_processed, total_files, rel_str)
                if on_category_progress:
                    on_category_progress(cat_name, cat_processed, cat_total, rel_str)

            self._log(f"📁 类型完成: {cat_name}")

        with ThreadPoolExecutor(max_workers=min(len(categories), self.max_category_workers)) as cat_executor:
            futures = {}
            for cat_name, files in grouped.items():
                if cancel_check and cancel_check():
                    break
                fut = cat_executor.submit(_download_one_category, cat_name, files)
                futures[fut] = cat_name

            for fut in as_completed(futures):
                if cancel_check and cancel_check():
                    break

        return failed
