# -*- coding: utf-8 -*-
"""ima_auth.py — v1.0.8 扫码登录 / 会话管理 / 自动续期

零客户端依赖：微信扫码 → ima 账号票据（IMA-TOKEN 2h / IMA-REFRESH-TOKEN 30d）。
- 登录流程与 ima.qq.com 网页端一致（open.weixin.qq.com qrconnect → auth_login/login）
- refresh 端点：POST /cgi-bin/auth_login/refresh {user_id, refresh_token, token_type}
- 会话明文保存在本工具目录 ima_session.json（仅本机可见；包含访问票据，勿外传）
"""
import json
import os
import random
import re
import threading
import time
from typing import Callable, Optional

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
APPID = "wx0d63f5de059f1d52"
REDIRECT_URI = "https://ima.qq.com/login#/weixin-login?retrySession=default"
LOGIN_API = "https://ima.qq.com/cgi-bin/auth_login/login"
REFRESH_API = "https://ima.qq.com/cgi-bin/auth_login/refresh"

SESSION_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "ima_session.json")
TOKEN_VALID_SECONDS = 7200  # 服务器返回 token_valid_time=7200
REFRESH_MARGIN = 600        # 剩余 <10 分钟时自动续期


def _js_bkn(token: str) -> int:
    """ima 的 bkn：h=5381; h+=(h<<5)+cc（JS int32 语义）。"""
    h = 5381
    for ch in token:
        h = (h + ((h << 5) & 0xFFFFFFFF) + ord(ch)) & 0xFFFFFFFF
    return h & 0x7FFFFFFF


class ImaSession:
    """登录态：cookie / bkn / 自动续期。线程安全（简单锁）。"""

    def __init__(self):
        self._lock = threading.Lock()
        self.data = {}
        self._set_cookies = {}
        self.load()

    # ── persistence ─────────────────────────────────────────────
    def load(self):
        try:
            with open(SESSION_FILE, "r", encoding="utf-8") as f:
                j = json.load(f)
            self.data = j.get("response", j) if isinstance(j, dict) else {}
            sc = j.get("set_cookies") if isinstance(j, dict) else None
            self._set_cookies = sc if isinstance(sc, dict) else {}
        except Exception:
            self.data = {}
            self._set_cookies = {}
        # 登录响应体里 refresh_token 可能为空，票据有时只随 Set-Cookie 下发
        if not self.data.get("refresh_token"):
            rt = self._set_cookies.get("IMA-REFRESH-TOKEN")
            if rt:
                self.data["refresh_token"] = rt

    def save(self):
        try:
            with open(SESSION_FILE, "w", encoding="utf-8") as f:
                json.dump({"response": self.data,
                           "set_cookies": getattr(self, "_set_cookies", {}),
                           "saved_at": time.time()},
                          f, ensure_ascii=False, indent=1)
        except Exception:
            pass

    # ── state ──────────────────────────────────────────────────
    def is_logged_in(self) -> bool:
        d = self.data
        return bool(d.get("token") and d.get("user_id"))

    def token_age_seconds(self) -> float:
        saved = None
        try:
            with open(SESSION_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f).get("saved_at")
        except Exception:
            pass
        if not saved:
            return TOKEN_VALID_SECONDS * 10  # 旧会话文件无时间戳 → 视为可能过期
        return time.time() - float(saved)

    def cookie_str(self) -> str:
        d = self.data
        return ("IMA-UID=%s; IMA-TOKEN=%s; IMA-REFRESH-TOKEN=%s; UID-TYPE=%s; TOKEN-TYPE=%s"
                % (d.get("user_id", ""), d.get("token", ""), d.get("refresh_token", ""),
                   d.get("id_type", 0), d.get("token_type", 0)))

    def bkn(self) -> int:
        return _js_bkn(self.data.get("token") or "")

    def auth_headers(self) -> dict:
        cs = self.cookie_str()
        return {
            "User-Agent": UA,
            "Content-Type": "application/json; charset=utf-8",
            "Cookie": cs, "x-ima-cookie": cs,
            "x-ima-bkn": str(self.bkn()),
            "from_browser_ima": "1",
            "Origin": "https://ima.qq.com",
            "Referer": "https://ima.qq.com/",
        }

    # ── refresh ────────────────────────────────────────────────
    def refresh(self) -> bool:
        """换新 token。refresh_token 有则带上（30 天有效）；
        实测票据仍有效时即使无 refresh_token 也能续期。成功返回 True。"""
        with self._lock:
            d = self.data
            if not (d.get("token") and d.get("user_id")):
                return False
            body = {"user_id": d.get("user_id"),
                    "refresh_token": d.get("refresh_token"),
                    "token_type": d.get("token_type")}
            try:
                r = requests.post(REFRESH_API, json=body,
                                   headers=self.auth_headers(), timeout=30)
                j = r.json() if r.status_code == 200 else {}
                data = (j.get("data") or {}) if isinstance(j, dict) else {}
                if j.get("code") == 0 and data.get("token"):
                    d["token"] = data["token"]
                    if data.get("refresh_token"):
                        d["refresh_token"] = data["refresh_token"]
                    self.save()
                    return True
            except Exception:
                pass
            return False

    def ensure_fresh(self, on_log: Optional[Callable[[str], None]] = None) -> bool:
        """登录态检查 + 必要时自动续期。返回是否可用。"""
        if not self.is_logged_in():
            return False
        age = self.token_age_seconds()
        if age < TOKEN_VALID_SECONDS - REFRESH_MARGIN:
            return True  # 票据仍在安全窗口内
        if on_log:
            on_log("⏳ 登录票据临近过期，正在自动续期…")
        if self.refresh():
            if on_log:
                on_log("✅ 票据已自动续期（无需重新扫码）")
            return True
        if on_log:
            on_log("⚠️ 自动续期失败，请重新扫码登录")
        return False


# ── QR 登录流程 ──────────────────────────────────────────────────
def login_flow(session: ImaSession,
               on_log: Callable[[str], None],
               on_qr: Callable[[str], None],
               cancel_check: Optional[Callable[[], bool]] = None,
               deadline_s: int = 330) -> bool:
    """扫码登录主流程（阻塞；GUI 在工作线程调用）。

    on_qr(qr_png_path)：二维码图片已保存，回调负责展示。
    返回 True=登录成功（session 已持久化）。
    """
    # 1) 取 uuid + 下载二维码
    ts = int(time.time() * 1000)
    qrc = ("https://open.weixin.qq.com/connect/qrconnect"
           "?appid=%s&scope=snsapi_login&redirect_uri=%s&state="
           "&login_type=jssdk&self_redirect=true&styletype=&sizetype=&bgcolor="
           "&rst=&ts=%d&style=white&href=&lang=cn&stylelite=1&fast_login=1"
           % (APPID, requests.utils.quote(REDIRECT_URI, safe=""), ts))
    r = requests.get(qrc, headers={"User-Agent": UA,
                                   "Referer": "https://ima.qq.com/"}, timeout=30)
    m = (re.search(r"uuid[\"'\s:=]+([A-Za-z0-9_=-]{12,})[\"']", r.text)
         or re.search(r"window\.uuid\s*=\s*[\"']([^\"']+)[\"']", r.text))
    if not m:
        on_log("❌ 获取登录二维码失败（微信端未返回 uuid），请稍后重试")
        return False
    uuid = m.group(1)
    qr = requests.get("https://open.weixin.qq.com/connect/qrcode/" + uuid,
                      headers={"User-Agent": UA, "Referer": qrc}, timeout=30)
    qr_path = os.path.join(os.path.dirname(SESSION_FILE), "ima_login_qr.png")
    with open(qr_path, "wb") as f:
        f.write(qr.content)
    on_log("📱 请用微信扫描二维码，并在手机上点击「确认」")
    on_qr(qr_path)

    # 2) 长轮询等待确认
    t0 = time.time()
    last, scanned_shown = "", False
    wx_code = None
    while time.time() - t0 < deadline_s:
        if cancel_check and cancel_check():
            on_log("已取消扫码登录")
            return False
        try:
            rr = requests.get("https://lp.open.weixin.qq.com/connect/l/qrconnect",
                              params={"uuid": uuid, "last": last,
                                      "_": int(time.time() * 1000)},
                              headers={"User-Agent": UA}, timeout=45)
        except requests.Timeout:
            continue
        except Exception:
            time.sleep(2)
            continue
        mc = re.search(r"wx_errcode=(\d+)", rr.text)
        if not mc:
            time.sleep(2)
            continue
        ec = mc.group(1)
        last = ec
        if ec == "405":
            mm = re.search(r"wx_code='([^']+)'", rr.text) \
                or re.search(r'wx_code="([^"]+)"', rr.text)
            if mm:
                wx_code = mm.group(1)
            else:
                on_log("⚠️ 微信已确认但未取到授权码（响应格式异常），"
                       "内容片段：%r" % rr.text[:160])
            break
        if ec == "404" and not scanned_shown:
            on_log("✅ 已扫码，请在手机上点击确认")
            scanned_shown = True
        elif ec == "403":
            on_log("❌ 二维码已失效或被拒绝，请重新点「扫码登录」")
            return False
    if not wx_code:
        on_log("❌ 未在限时内完成确认，请重新扫码")
        return False

    # 3) auth_login/login —— 与 ima 网页前端逐字段一致（含设备指纹，防风控）
    q = "".join(random.choice("0123456789abcdef") for _ in range(38))
    dev_cookie = ("IMA-GUID=guid-%s; IMA-Q36=%s; IMA-IUA=%s; PLATFORM=H5; "
                  "CLIENT-TYPE=256053; WEB-VERSION=999.999.999"
                  % (q, q, UA.replace(";", ",")))
    bodies = [
        {"account_type": 2, "code": wx_code, "auth_appid": APPID,
         "client_info": {"guid": "guid-" + q, "platform": 4, "qimei36": q}},
        {"account_type": 2, "code": wx_code, "auth_appid": APPID,
         "client_info": {"platform": 4}},
    ]
    sess = requests.Session()
    sess.headers.update({"User-Agent": UA,
                        "Content-Type": "application/json; charset=utf-8",
                        "x-ima-cookie": dev_cookie, "from_browser_ima": "1",
                        "Origin": "https://ima.qq.com",
                        "Referer": "https://ima.qq.com/"})
    for i, body in enumerate(bodies):
        sess.headers["x-ima-cookie"] = dev_cookie if i == 0 else ""
        try:
            r = sess.post(LOGIN_API, json=body, timeout=(15, 60))
        except Exception as e:
            on_log("⚠️ 登录接口网络异常：%s" % type(e).__name__)
            continue
        try:
            j = r.json()
        except Exception:
            on_log("⚠️ 登录接口返回异常（HTTP %s，非 JSON）" % r.status_code)
            continue
        if isinstance(j, dict) and j.get("code") == 0:
            # ima 登录响应为扁平结构（token/user_id 在顶层，无 data 包装）；
            # 兼容旧探针的嵌套 data 形态，两者取其一
            data = j.get("data") if isinstance(j.get("data"), dict) else {}
            if not (data.get("token") or data.get("user_id")
                    or data.get("userId")):
                data = j

            def pick(*names):
                for n in names:
                    if data.get(n) not in (None, ""):
                        return data[n]
                return None
            # refresh_token 三路兜底：响应体 → requests 解析的 Cookie → 原始 Set-Cookie 头
            # （cookiejar 会静默丢弃无法解析的 Cookie，必须再扫一遍原始头）
            rt = pick("refresh_token", "refreshToken")
            if not rt:
                try:
                    rt = sess.cookies.get("IMA-REFRESH-TOKEN") or None
                except Exception:
                    rt = None
            if not rt:
                try:
                    raw_sc = r.raw.headers.get_all("Set-Cookie") or []
                except Exception:
                    raw_sc = []
                for sc in raw_sc:
                    mm = re.search(r"IMA-REFRESH-TOKEN=([^;]+)", sc)
                    if mm and mm.group(1).strip():
                        rt = mm.group(1).strip()
                        break
            session.data = {
                "token": pick("token"),
                "refresh_token": rt,
                "user_id": pick("user_id", "userId"),
                "id_type": pick("id_type", "idType"),
                "token_type": pick("token_type", "tokenType"),
            }
            if session.data["token"] and session.data["user_id"]:
                session.save()
                if rt:
                    on_log("✅ 登录成功，会话已保存（30 天内免扫码）")
                else:
                    on_log("✅ 登录成功（票据 2 小时有效，临近过期会自动续期）")
                return True
            # code=0 却没拿到票据：把完整响应落盘供排查，不再重试（授权码已消费）
            try:
                dbg = os.path.join(os.path.dirname(SESSION_FILE),
                                   "ima_login_debug.json")
                with open(dbg, "w", encoding="utf-8") as f:
                    json.dump(j, f, ensure_ascii=False, indent=1)
                on_log("⚠️ ima 返回 code=0 但未找到票据字段，响应已存到 %s "
                       "（顶层字段：%s）" % (dbg, sorted(j.keys())))
            except Exception:
                on_log("⚠️ ima 返回 code=0 但未找到票据字段（调试落盘失败）")
            return False
        else:
            on_log("⚠️ ima 拒绝登录：HTTP %s code=%s msg=%s"
                   % (r.status_code,
                      j.get("code") if isinstance(j, dict) else "?",
                      j.get("msg") if isinstance(j, dict) else "?"))
    on_log("❌ 登录失败（ima 未返回票据），请重试")
    return False


_SHARED = ImaSession()


def get_session() -> ImaSession:
    return _SHARED
