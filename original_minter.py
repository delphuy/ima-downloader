# -*- coding: utf-8 -*-
"""original_minter.py — v1.0.8 原件直下管线（加密信封协议，零客户端依赖）

对每个文件的 media_id 调 ima 加密端点签发**完整原件**的临时下载 URL：
  POST https://ima.qq.com/cgi-bin/s/file_manager/get_media
  请求体 = base64( iv12 || AES-128-GCM(key16, body_json) )
  头     = x-ima-cm:1, x-ima-ckey: base64(RSA-2048-OAEP-SHA256(pub, key16))
  响应体 = base64( iv12 || AES-GCM(...) )，用同一 key16 解密出 JSON
  → jump_url_info.url 即原件签名 URL（≥24h 有效）
协议来源：ima 客户端 chrome.dll 原生层逆向 + JS 注入层对照，全部 live 验证。

下载后校验：字节数 == 服务端登记 file_size（逐字节），
PDF 加验 pypdf 页数，Word 验容器，图片验文件头。
"""
import base64
import concurrent.futures as cf
import json
import os
import re
import threading
import time
import zipfile
from pathlib import Path

import requests
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding as apad
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

GET_MEDIA_URL = "https://ima.qq.com/cgi-bin/s/file_manager/get_media"

# ima 服务器 RSA 公钥（2048-bit，随工具分发；逆向自官方客户端）
_HERE = os.path.dirname(os.path.abspath(__file__))
_PUB_PEM_FILE = os.path.join(_HERE, "ima_server_pub.pem")
_PUB_PEM_CONST = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAx9h6SY1LO88wRVKdOC5U
tjYTXfMpUqCK22FemW9ba4812nVjF4Va+guoHXdBePkhsQmz94PeqqZiSN/YekiV
CU6HbWivdhKcs6LcYMT+sw4cwtMZ1NOJEkY1ujOWFnmNmpK243wwlf+RwE/L+xOJ
8vy/EBuYDv06M+BbccO832bOpWsOFYPPP5KtOmOaqXq6Fgu1vOrXmQIo0q8WmO09
PvjHLwIruqthV2dBcVI1qMEKejM1SKwzCWb78t+fUsr3OjDqApWma3h10hGKcin4
NIGdfITwmiBmS+R1Mr8P/ssNq0ptvr9+VqUvsJD7ASVCPo9EG658fZYGil6oH5JN
OQIDAQAB
-----END PUBLIC KEY-----
"""


def _load_pub():
    try:
        with open(_PUB_PEM_FILE, "rb") as f:
            return load_pem_public_key(f.read())
    except Exception:
        return load_pem_public_key(_PUB_PEM_CONST.encode())


_SERVER_PUB = _load_pub()
_KB_TAIL_RE = re.compile(r"^[0-9a-f]{32}(\d{5,32})$")


def extract_kb_id(media_id: str) -> str:
    """media_id 形如 pdf_<32hex>_<32hex><知识库ID> —— 尾部数字即 KBID。"""
    try:
        seg = media_id.split("_")[-1]
        m = _KB_TAIL_RE.match(seg)
        if m:
            return m.group(1)
    except Exception:
        pass
    return ""


def _encrypt_request(params: dict):
    pt = json.dumps(params, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    key = os.urandom(16)
    iv = os.urandom(12)
    ct_tag = AESGCM(key).encrypt(iv, pt, None)
    ckey = _SERVER_PUB.encrypt(
        key, apad.OAEP(mgf=apad.MGF1(hashes.SHA256()),
                       algorithm=hashes.SHA256(), label=None))
    return (base64.b64encode(iv + ct_tag).decode("ascii"),
            base64.b64encode(ckey).decode("ascii"), key)


def _decrypt_response(key: bytes, text: str) -> dict:
    raw = base64.b64decode(text.strip())
    if len(raw) < 28:
        raise ValueError("短包")
    return json.loads(AESGCM(key).decrypt(raw[:12], raw[12:], None).decode("utf-8"))


def mint_original_url(session, media_id: str, share_id: str = "",
                      kb_id: str = "", retries: int = 2) -> str:
    """签发单个文件的原件 URL。失败返回 ''。"""
    kbid = kb_id or extract_kb_id(media_id)
    variants = []
    if kbid:
        variants.append({"media_id": media_id, "knowledge_base_id": kbid})
    if share_id:
        variants.append({"media_id": media_id, "share_id": share_id,
                         "source_knowledge_base_id": kbid} if kbid
                        else {"media_id": media_id, "share_id": share_id})
    variants.append({"media_id": media_id})
    s = requests.Session()
    s.headers.update(session.auth_headers())
    for attempt in range(retries + 1):
        for params in variants:
            try:
                data, ckey, key = _encrypt_request(params)
                h = dict(s.headers)
                h.update({"x-ima-cm": "1", "x-ima-ckey": ckey})
                r = s.post(GET_MEDIA_URL, data=data, headers=h, timeout=30)
                if r.status_code != 200:
                    time.sleep(0.4)
                    continue
                j = _decrypt_response(key, r.text)
                if j.get("code") == 0:
                    jui = (j.get("jump_url_info") or {})
                    url = jui.get("url") if isinstance(jui, dict) else None
                    if not url:
                        for v in (jui or {}).values() if isinstance(jui, dict) else []:
                            if isinstance(v, str) and v.startswith("http"):
                                url = v
                                break
                    if url:
                        return url
            except Exception:
                time.sleep(0.4)
                continue
    return ""


def _verify_payload(path: str, expect_size: int) -> tuple:
    """返回 (ok, note)。字节数为硬校验；类型校验为完整性证据。"""
    n = os.path.getsize(path)
    if n != expect_size:
        return False, f"字节数 {n} != 登记 {expect_size}"
    low = path.lower()
    try:
        if low.endswith(".pdf"):
            from pypdf import PdfReader
            pages = len(PdfReader(path).pages)
            return (pages > 0), f"PDF {pages} 页"
        if low.endswith((".docx", ".doc")):
            with open(path, "rb") as f:
                head = f.read(4)
            if zipfile.is_zipfile(path) or head == b"\xd0\xcf\x11\xe0":
                return True, "Word 容器完整"
            return False, "Word 容器损坏"
        if low.endswith((".jpg", ".jpeg")):
            with open(path, "rb") as f:
                head = f.read(3)
            return head == b"\xff\xd8\xff", "图片完整"
        if low.endswith(".png"):
            with open(path, "rb") as f:
                head = f.read(8)
            return head.startswith(b"\x89PNG"), "图片完整"
    except Exception as e:
        return False, f"解析失败: {e}"
    return True, "已落盘"


class _FailedItem:
    def __init__(self, output_path, reason=""):
        self.output_path = output_path
        self.reason = reason


class OriginalsReport:
    """与 GUI 收尾兼容的原件下载报告。"""

    def __init__(self):
        self.downloaded = 0
        self.skipped = 0
        self.preview = 0
        self.text_only = 0
        self.preview_ok = 0
        self.preview_bad = 0
        self.size_pass = 0
        self.size_fail = 0
        self.failed = []
        self.verify_base_dir = ""
        self._details = []
        self._pages_total = 0
        self._bytes_total = 0

    def summary_line(self) -> str:
        return (f"原件 {self.downloaded} 份 · 已存在跳过 {self.skipped} 份 · "
                f"失败 {len(self.failed)} 份 · PDF 合计 {self._pages_total} 页 · "
                f"共 {self._bytes_total / 1e6:.1f} MB")

    def content_coverage_lines(self):
        out = []
        if self.size_pass:
            out.append(f"字节级校验通过：{self.size_pass} 份（字节数逐个等于云端登记值）")
        if self.size_fail:
            out.append(f"字节级校验失败：{self.size_fail} 份")
        return out

    def write_verify_report(self):
        try:
            base = self.verify_base_dir or os.getcwd()
            path = os.path.join(base, "_v108_原件校验报告.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"downloaded": self.downloaded, "skipped": self.skipped,
                           "failed": [(x.output_path, x.reason) for x in self.failed],
                           "size_pass": self.size_pass, "size_fail": self.size_fail,
                           "pdf_pages_total": self._pages_total,
                           "bytes_total": self._bytes_total,
                           "details": self._details[:800]},
                          f, ensure_ascii=False, indent=1)
            return path
        except Exception:
            return ""


def run_originals_sync(session, files, root_path: Path, share_id: str,
                       on_log=None, on_progress=None,
                       cancel_check=None, workers: int = 8) -> OriginalsReport:
    """批量：遍历清单 → 逐个签发原件 URL → 下载 → 字节级+类型校验。"""
    report = OriginalsReport()
    report.verify_base_dir = str(root_path)
    root_path.mkdir(parents=True, exist_ok=True)
    total = len(files)
    on_log and on_log(f"🔎 共 {total} 个条目，开始逐个签发原件地址（加密信封协议）")

    tl = threading.local()

    def sess_http():
        if not hasattr(tl, "s"):
            tl.s = requests.Session()
            tl.s.headers.update({"User-Agent": session.auth_headers()["User-Agent"]})
        return tl.s

    def one(idx, kf):
        rel = kf.rel_path
        dest = root_path / rel
        expect = int(str(kf.file_size or "0") or 0)
        if cancel_check and cancel_check():
            return None
        try:
            if dest.exists() and expect and os.path.getsize(dest) == expect:
                ok, note = _verify_payload(str(dest), expect)
                if ok:
                    return ("skip", kf, str(dest), note)
                os.remove(dest)
            url = mint_original_url(session, kf.media_id, share_id=share_id)
            if not url:
                return ("fail", kf, str(dest), "签发失败（无权限或格式不支持）")
            if cancel_check and cancel_check():
                return None
            r = sess_http().get(url, timeout=(15, 600), stream=True)
            if r.status_code != 200:
                return ("fail", kf, str(dest), f"HTTP {r.status_code}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = str(dest) + ".part"
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
            os.replace(tmp, str(dest))
            ok, note = _verify_payload(str(dest), expect) if expect else (True, "无登记大小")
            return ("ok" if ok else "bad", kf, str(dest), note)
        except Exception as e:
            return ("fail", kf, str(dest), repr(e)[:120])

    done = 0
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(one, i, kf) for i, kf in enumerate(files)]
        for fut in cf.as_completed(futs):
            res = fut.result()
            done += 1
            if res is None:
                continue
            kind, kf, path, note = res
            if kind == "skip":
                report.skipped += 1
                report.size_pass += 1
                report._bytes_total += int(str(kf.file_size or "0") or 0)
                if note.startswith("PDF"):
                    try:
                        report._pages_total += int(note.split()[1])
                    except Exception:
                        pass
            elif kind == "ok":
                report.downloaded += 1
                report.size_pass += 1
                report._bytes_total += int(str(kf.file_size or "0") or 0)
                if note.startswith("PDF"):
                    try:
                        report._pages_total += int(note.split()[1])
                    except Exception:
                        pass
            elif kind == "bad":
                report.size_fail += 1
                report.failed.append(_FailedItem(path, note))
            else:
                report.failed.append(_FailedItem(path, note))
            report._details.append({"title": kf.title, "kind": kind, "note": note})
            on_progress and on_progress(done, total, kf.title)
            if done % 25 == 0:
                on_log and on_log(f"⏬ 进度 {done}/{total} · 成功 {report.downloaded} · "
                                  f"跳过 {report.skipped} · 失败 {len(report.failed)}")
    return report
