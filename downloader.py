# downloader.py - 文件下载器
# 对应 Java 版本的 FileDownloader.java + KnowledgeProcessor.java

import os
import re
import shutil
import subprocess
import threading
import requests
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Callable, Optional, Set
from urllib.parse import urlparse
import mimetypes

from models import (
    KnowledgeItem, FailedDownload, KnowledgeFile, MediaTypeInfo, DownloadReport,
)

try:  # v1.0.4: 官方 OpenAPI 引擎（缺 requests 以外的依赖时仍可匿名回退）
    from api_service import ImaOpenApiService, ImaApiError
except ImportError:  # pragma: no cover
    ImaOpenApiService = None
    ImaApiError = Exception


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


def strip_image_mogr(url: str) -> str:
    """剥离 COS 的 imageMogr2 图片处理参数。

    实测结论（v1.0.4 根因分析）：
    - imageMogr2 查询参数不参与 COS 签名，剥离后签名依然有效；
    - media_type=9 图片条目：cover_urls[0] 剥离后即原始文件字节
      （6/6 与服务端 file_size 逐字节一致）；
    - PDF/Word 条目：cover_urls[0] 是服务端渲染的首页图
      （*_preview_p1.jpg），剥离 size-limit 后为高清版。
    """
    if not url:
        return ""
    idx = url.find("&imageMogr2/")
    if idx != -1:
        return url[:idx]
    idx = url.find("?imageMogr2/")
    if idx != -1:
        return url[:idx]
    return url


# ── v1.0.4 匿名回退链（遍历时确定来源类型）─────────────────────

def resolve_item_download(item: KnowledgeItem):
    """匿名模式下确定一个条目的可用下载地址与来源类型。

    返回 (url, source_kind)：
      original       jump_url 原件（老格式分享链接）
      image-original 图片条目，cover_urls[0] 去 imageMogr2 即原件字节
      preview        PDF/Word 等文档，仅能取首页渲染图
      metadata       无任何文件地址，仅能落解析文本/摘要
    """
    url = extract_download_url(item.jump_url)
    if url:
        return url, "original"

    if item.cover_urls:
        cover = strip_image_mogr(item.cover_urls[0])
        if cover:
            # media_type=9 为图片：cover 即原件本身
            if item.media_type == 9:
                return cover, "image-original"
            return cover, "preview"

    return "", "metadata"


def resolve_download_url(kf: KnowledgeFile, openapi=None):
    """下载时解析最终地址：官方 OpenAPI 原件优先，失败回退匿名链。

    返回 (url, source_kind)。openapi 为 ImaOpenApiService 或 None；
    服务内部鉴权失败会自禁用，后续条目直接走匿名链，不再反复试探。
    """
    if (
        openapi is not None
        and getattr(openapi, "available", False)
        and kf.media_id
        and kf.source_kind != "original"   # jump_url 原件无需再查
    ):
        try:
            url = openapi.get_media_url(kf.media_id, title=kf.title)
            if url:
                return url, "original"
        except Exception:
            pass
    return kf.url, kf.source_kind


def _write_text_products(base_dir: Path, kf: KnowledgeFile, log=None) -> int:
    """落盘解析文本 / AI 摘要附加产物（v1.0.5 起仅在 save_texts=True 时调用）。

    注意：summary_text 是服务端 introduction 字段的开头摘录（实测约 200-300 字，
    多为目录/开头片段），不是文档全文。返回写入的文件数（0=无可写内容）。
    """
    if not kf.summary_text:
        return 0
    written = 0
    stem = Path(kf.rel_path).stem
    parent = base_dir / Path(kf.rel_path).parent
    try:
        parent.mkdir(parents=True, exist_ok=True)
        text_path = parent / f"{stem}_解析文本.txt"
        if not text_path.exists():
            text_path.write_text(kf.summary_text, encoding="utf-8")
            written += 1
            if log:
                log(f"[TEXT] {text_path.relative_to(base_dir).as_posix()}")
        if getattr(kf, "abstract_text", ""):
            abs_path = parent / f"{stem}_摘要.txt"
            if not abs_path.exists():
                abs_path.write_text(kf.abstract_text, encoding="utf-8")
                written += 1
                if log:
                    log(f"[TEXT] {abs_path.relative_to(base_dir).as_posix()}")
    except Exception as e:
        if log:
            log(f"[WARN] 文本产物写入失败 {kf.rel_path}: {e}")
    return written


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

    # 1.5 v1.0.4 图片条目：cover URL 即原始文件，取其真实扩展名（比类型推断准）
    if item is not None and getattr(item, "media_type", 0) == 9 and download_url:
        try:
            _p = urlparse(strip_image_mogr(download_url))
            _ue = os.path.splitext(_p.path)[1]
            if _ue and len(_ue) > 1:
                return safe + _ue
        except Exception:
            pass

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


# ── v1.0.6: 逐文件字节校验（下载完成 ≠ 下载完整，必须实测比对）─────

def _is_link_content(kf: KnowledgeFile) -> bool:
    """链接/URL 类型条目（受「打印PDF」开关控制的那类）。"""
    rel = str(getattr(kf, "rel_path", "") or "").lower()
    if rel.endswith(('.url', '.html')):
        return True
    title = (getattr(kf, "title", "") or "").lower()
    return bool(title) and any(k in title for k in ['链接', 'link', 'url'])


def _find_actual_file(out_path: Path) -> Optional[Path]:
    """找回实际落盘文件。

    download_single_file 可能按响应头修正扩展名（ensure_extension_from_response），
    也可能把验证页转成 .url 并删原文件。这里按 期望路径 → 同名不同扩展 顺序找回。
    """
    if out_path.exists():
        return out_path
    candidates = [
        p for p in out_path.parent.glob(out_path.stem + ".*")
        if p.is_file() and p.suffix.lower() != ".url"
    ]
    if len(candidates) == 1:
        return candidates[0]
    if candidates:
        return max(candidates, key=lambda p: p.stat().st_mtime)
    return None


def verify_downloaded_file(
    out_path: Path,
    kf: KnowledgeFile,
    kind: str,
    rel_str: str,
    note: str = "",
) -> tuple:
    """v1.0.6: 校验单个已下载文件，返回 (计数键, 排序优先级, 相对路径, 报告行)。

    - original / image-original: 实际字节数 == 服务端 file_size → ✅（真正的自测比对）
    - preview: 文件存在且 JPEG 魔数合法 → 🔍（首页预览，非原件）
    - 找不到文件 / 魔数非法 → ❌
    note: 附加标记（如 "已存在·"），用于区分跳过文件的就地校验。
    """
    try:
        expected = int(str(getattr(kf, "file_size", "") or "").strip() or 0)
    except (TypeError, ValueError):
        expected = 0

    actual_file = _find_actual_file(out_path)
    if actual_file is None:
        return ("size_fail", 0, rel_str,
                f"[❌文件缺失{note}] {rel_str} — 记录为成功但磁盘上未找到文件")
    actual = actual_file.stat().st_size

    if kind in ("original", "image-original"):
        if expected > 0 and actual != expected:
            return ("size_fail", 0, rel_str,
                    f"[❌字节不符{note}] {rel_str} — 实际 {actual:,} B ≠ 服务端上报 {expected:,} B（不完整/损坏）")
        if expected > 0:
            return ("size_pass", 2, rel_str,
                    f"[✅字节一致{note}] {rel_str} — {actual:,} B == 服务端上报 {expected:,} B")
        return ("size_pass", 2, rel_str,
                f"[✅已下载{note}] {rel_str} — {actual:,} B（服务端未上报大小，无法比对）")

    # kind == "preview"：预览图只做存在性 + JPEG 魔数校验
    try:
        with actual_file.open("rb") as f:
            magic = f.read(2)
    except OSError:
        magic = b""
    if actual == 0 or magic != b"\xff\xd8":
        return ("preview_bad", 0, rel_str,
                f"[❌预览异常{note}] {rel_str} — 非法图片（{actual:,} B，非JPEG），需重下")
    orig_note = f"原件 {expected:,} B" if expected > 0 else "原件大小未知"
    return ("preview_ok", 1, rel_str,
            f"[🔍首页预览{note}] {rel_str} — 合法JPEG {actual:,} B（{orig_note}，"
            f"平台策略限制：匿名链路与已加入库的 OpenAPI 均不签发该原件地址；"
            f"v1.0.7：在 ima 客户端打开过该文档后，可用「收割通道」补齐完整原件并核对页数）")


def _apply_verify_result(report: DownloadReport, result: tuple, stats_lock: threading.Lock) -> None:
    """把 verify_downloaded_file 的结果累计进 report（线程安全）。"""
    key, prio, rel, line = result
    with stats_lock:
        if key == "size_pass":
            report.size_pass += 1
        elif key == "size_fail":
            report.size_fail += 1
        elif key == "preview_ok":
            report.preview_ok += 1
        elif key == "preview_bad":
            report.preview_bad += 1
        report.verify_rows.append((prio, rel, line))


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
        openapi=None,
        save_texts: bool = False,
    ) -> DownloadReport:
        """新统一接口：按 KnowledgeFile.rel_path 存放文件，正确重建目录结构。

        v1.0.4:
        - openapi: ImaOpenApiService 或 None。有凭证时优先取原件地址。
        - preview 类型文件名加 .首页预览 后缀，避免用户误认为原件。
        v1.0.5:
        - save_texts 默认 False：1 个条目只落 1 个文件（原件/预览图），
          不再自动生成 _解析文本.txt / _摘要.txt（用户反馈 3 文件拥挤）。
          传 True 才写文本产物；无原件地址且未保存文本的条目记 [MISS]。
        返回 DownloadReport（成功分类统计 + 失败清单）。
        """
        report = DownloadReport()
        base_dir.mkdir(parents=True, exist_ok=True)
        report.verify_base_dir = str(base_dir)  # v1.0.6: 校验报告落盘位置

        if existing_rels is None:
            existing_rels = set()

        total = len(files)
        processed = 0
        stats_lock = threading.Lock()

        def _count(kind: str):
            with stats_lock:
                if kind == "original":
                    report.original += 1
                elif kind == "image-original":
                    report.image_original += 1
                elif kind == "preview":
                    report.preview += 1

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {}
            for kf in files:
                if cancel_check and cancel_check():
                    break
                if not str(kf.rel_path):
                    continue

                url, kind = resolve_download_url(kf, openapi)

                out_path = base_dir / kf.rel_path
                if kind == "preview":
                    out_path = out_path.with_name(out_path.stem + ".首页预览.jpg")
                rel_str = out_path.relative_to(base_dir).as_posix()

                # v1.0.5: 文本产物默认不落盘（1 个条目 1 个文件），save_texts=True 才写
                texts_written = _write_text_products(base_dir, kf, log=self._log) if save_texts else 0

                if not url:
                    # 无原件地址（服务端 jump_url 为空）——不再静默丢弃
                    if texts_written:
                        self._log(f"[TEXT-ONLY] {rel_str} （无原件地址，已保存解析文本/摘要）")
                        with stats_lock:
                            report.text_only += 1
                            report.verify_rows.append((3, rel_str,
                                f"[⏸仅文本] {rel_str} — 无原件地址，仅保存了解析文本/摘要"))
                    else:
                        # 未产出任何文件：不计入成功统计，仅日志说明
                        self._log(f"[MISS] {rel_str} （服务端无原件地址；勾选「保存解析文本/摘要」可保存文本摘录）")
                        with stats_lock:
                            report.verify_rows.append((3, rel_str,
                                f"[⏸无地址] {rel_str} — 服务端未提供任何文件地址，未产出文件"))
                    processed += 1
                    if on_progress:
                        on_progress(processed, total, rel_str)
                    continue

                # 链接 / URL 类型内容：受 enable_print_pdf 控制
                is_link_type = _is_link_content(kf)
                if is_link_type or (kf.title and any(k in kf.title.lower() for k in ['链接', 'link', 'url'])):
                    if rel_str in existing_rels or (out_path.with_suffix('.pdf').exists() or out_path.exists()):
                        self._log(f"[SKIP] {rel_str}")
                        with stats_lock:
                            report.skipped += 1
                    else:
                        if enable_print_pdf:
                            pdf_path = out_path.with_suffix(".pdf")
                            if print_url_to_pdf(kf.url, pdf_path):
                                self._log(f"[PDF] {rel_str} （浏览器打印生成PDF）")
                                _count("original")
                            else:
                                url_file = out_path.with_suffix(".url")
                                url_file.parent.mkdir(parents=True, exist_ok=True)
                                with url_file.open("w", encoding="utf-8") as f:
                                    f.write("[InternetShortcut]\n")
                                    f.write(f"URL={kf.url}\n")
                                self._log(f"[LINK] {rel_str} （打印失败，已保存为链接）")
                                _count("original")
                        else:
                            url_file = out_path.with_suffix(".url")
                            url_file.parent.mkdir(parents=True, exist_ok=True)
                            with url_file.open("w", encoding="utf-8") as f:
                                f.write("[InternetShortcut]\n")
                                f.write(f"URL={kf.url}\n")
                            self._log(f"[LINK] {rel_str} （已保存为链接，未打印PDF）")
                            _count("original")
                    processed += 1
                    if on_progress:
                        on_progress(processed, total, rel_str)
                    continue

                if rel_str in existing_rels or out_path.exists():
                    self._log(f"[SKIP] {rel_str}")
                    with stats_lock:
                        report.skipped += 1
                    # v1.0.6: 已存在的文件也就地校验（不重下，但要比对字节）
                    _apply_verify_result(report, verify_downloaded_file(
                        out_path, kf, kind, rel_str, note="·已存在"), stats_lock)
                    processed += 1
                    if on_progress:
                        on_progress(processed, total, rel_str)
                    continue

                out_path.parent.mkdir(parents=True, exist_ok=True)
                fut = executor.submit(self._download_task, url, out_path, rel_str)
                futures[fut] = (url, out_path, rel_str, kind, kf)

            for fut in as_completed(futures):
                url, out_path, rel_str, kind, kf = futures[fut]
                exc = fut.exception()
                processed += 1
                if exc:
                    self._log(f"[FAIL] {rel_str} | {exc}")
                    report.failed.append(FailedDownload(download_url=url, output_path=out_path))
                    with stats_lock:
                        report.verify_rows.append((0, rel_str,
                            f"[❌下载失败] {rel_str} — {exc}"))
                else:
                    _count(kind)
                    # v1.0.6: 每个成功文件立即做字节级自测比对
                    _apply_verify_result(report, verify_downloaded_file(
                        out_path, kf, kind, rel_str), stats_lock)
                if on_progress:
                    on_progress(processed, total, rel_str)

        return report

    def download_grouped_files(
        self,
        grouped: dict[str, List[KnowledgeFile]],
        base_dir: Path,
        on_progress: Optional[Callable[[int, int, str], None]] = None,
        on_category_progress: Optional[Callable[[str, int, int, str], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
        existing_rels: Optional[Set[str]] = None,
        enable_print_pdf: bool = True,
        openapi=None,
        save_texts: bool = False,
    ) -> DownloadReport:
        """
        按内容类型分组下载（链接类型/文档类型/文章类型）。
        - 不同类型使用并行线程（最多 self.max_category_workers）
        - 同一类型的文件在同一个线程内顺序下载
        v1.0.4: 返回 DownloadReport；无原件地址的条目不再静默丢弃。
        v1.0.5: save_texts 默认 False——1 个条目只落 1 个文件，不自动生成
          _解析文本.txt / _摘要.txt；传 True 才写文本产物。
        """
        report = DownloadReport()
        base_dir.mkdir(parents=True, exist_ok=True)
        report.verify_base_dir = str(base_dir)  # v1.0.6: 校验报告落盘位置

        if existing_rels is None:
            existing_rels = set()

        categories = list(grouped.keys())
        total_files = sum(len(fs) for fs in grouped.values())
        global_processed = 0
        stats_lock = threading.Lock()

        def _count(kind: str):
            with stats_lock:
                if kind == "original":
                    report.original += 1
                elif kind == "image-original":
                    report.image_original += 1
                elif kind == "preview":
                    report.preview += 1

        def _download_one_category(cat_name: str, files: List[KnowledgeFile]):
            nonlocal global_processed
            cat_total = len(files)
            cat_processed = 0

            self._log(f"📁 开始类型: {cat_name} ({cat_total} 个文件)")

            for kf in files:
                if cancel_check and cancel_check():
                    return

                if not str(kf.rel_path):
                    continue

                url, kind = resolve_download_url(kf, openapi)

                out_path = base_dir / kf.rel_path
                if kind == "preview":
                    out_path = out_path.with_name(out_path.stem + ".首页预览.jpg")
                rel_str = out_path.relative_to(base_dir).as_posix()

                # v1.0.5: 文本产物默认不落盘（1 个条目 1 个文件），save_texts=True 才写
                texts_written = _write_text_products(base_dir, kf, log=self._log) if save_texts else 0

                if not url:
                    if texts_written:
                        self._log(f"[TEXT-ONLY] {rel_str} （无原件地址，已保存解析文本/摘要）")
                        with stats_lock:
                            report.text_only += 1
                            global_processed += 1
                            report.verify_rows.append((3, rel_str,
                                f"[⏸仅文本] {rel_str} — 无原件地址，仅保存了解析文本/摘要"))
                    else:
                        # 未产出任何文件：不计入成功统计，仅日志说明
                        self._log(f"[MISS] {rel_str} （服务端无原件地址；勾选「保存解析文本/摘要」可保存文本摘录）")
                        with stats_lock:
                            global_processed += 1
                            report.verify_rows.append((3, rel_str,
                                f"[⏸无地址] {rel_str} — 服务端未提供任何文件地址，未产出文件"))
                    if on_progress:
                        on_progress(global_processed, total_files, rel_str)
                    if on_category_progress:
                        on_category_progress(cat_name, cat_processed + 1, cat_total, rel_str)
                    cat_processed += 1
                    continue

                if rel_str in existing_rels or out_path.exists():
                    self._log(f"[SKIP] {rel_str}")
                    with stats_lock:
                        report.skipped += 1
                        global_processed += 1
                    # v1.0.6: 已存在的文件也就地校验（链接类内容无服务端大小可比，跳过）
                    if not _is_link_content(kf):
                        _apply_verify_result(report, verify_downloaded_file(
                            out_path, kf, kind, rel_str, note="·已存在"), stats_lock)
                    if on_progress:
                        on_progress(global_processed, total_files, rel_str)
                    if on_category_progress:
                        on_category_progress(cat_name, cat_processed + 1, cat_total, rel_str)
                    cat_processed += 1
                    continue

                # 链接特殊处理（受 print_pdf 勾选控制）
                is_link = _is_link_content(kf)
                if is_link:
                    if enable_print_pdf:
                        pdf_path = out_path.with_suffix(".pdf")
                        if print_url_to_pdf(kf.url, pdf_path):
                            self._log(f"[PDF] {rel_str} （浏览器打印生成PDF）")
                            _count("original")
                        else:
                            url_file = out_path.with_suffix(".url")
                            url_file.parent.mkdir(parents=True, exist_ok=True)
                            with url_file.open("w", encoding="utf-8") as f:
                                f.write("[InternetShortcut]\n")
                                f.write(f"URL={kf.url}\n")
                            self._log(f"[LINK] {rel_str} （打印失败，已保存为链接）")
                            _count("original")
                    else:
                        url_file = out_path.with_suffix(".url")
                        url_file.parent.mkdir(parents=True, exist_ok=True)
                        with url_file.open("w", encoding="utf-8") as f:
                            f.write("[InternetShortcut]\n")
                            f.write(f"URL={kf.url}\n")
                        self._log(f"[LINK] {rel_str} （已保存为链接，未打印PDF）")
                        _count("original")
                    with stats_lock:
                        global_processed += 1
                    if on_progress:
                        on_progress(global_processed, total_files, rel_str)
                    if on_category_progress:
                        on_category_progress(cat_name, cat_processed + 1, cat_total, rel_str)
                    cat_processed += 1
                    continue

                try:
                    download_single_file(url, out_path, timeout=self.timeout, on_log=self._log)
                    if kind == "preview":
                        self._log(f"🖼 [预览] {rel_str} （匿名模式仅能取首页图，填 OpenAPI 凭证可下原件）")
                    _count(kind)
                    # v1.0.6: 每个成功文件立即做字节级自测比对
                    _apply_verify_result(report, verify_downloaded_file(
                        out_path, kf, kind, rel_str), stats_lock)
                except Exception as e:
                    self._log(f"[FAIL] {rel_str} — {e}")
                    report.failed.append(FailedDownload(download_url=url, output_path=out_path))
                    with stats_lock:
                        report.verify_rows.append((0, rel_str,
                            f"[❌下载失败] {rel_str} — {e}"))

                with stats_lock:
                    global_processed += 1
                if on_progress:
                    on_progress(global_processed, total_files, rel_str)
                if on_category_progress:
                    on_category_progress(cat_name, cat_processed + 1, cat_total, rel_str)
                cat_processed += 1

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

        return report
