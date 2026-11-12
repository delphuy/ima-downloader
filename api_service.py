# api_service.py - IMA API 服务
# 对应 Java 版本的 ImaApiService.java

import threading
import time
import requests
from models import ShareInfoRequest, ShareInfoResponse, KnowledgeItem, CurrentPath, FolderInfo, MediaTypeInfo
from models import VersionMessage, Creator, CertificationInfo, CommentInfo, MemberInfo
from models import PermissionInfo, UserPermissionInfo, BasicInfo, KnowledgeBaseInfo


API_URL = "https://ima.qq.com/cgi-bin/knowledge_share_get/get_share_info"

# v1.0.4: 官方 OpenAPI（https://ima.qq.com/agent-interface 发凭证）
# 端点与认证头实测确认（无凭证返回 401 {"code":200002,"msg":"skill auth failed"}）
OPENAPI_BASE = "https://ima.qq.com/openapi/wiki/v1"
OPENAPI_AUTH_FAILED_CODES = {200002}


class ImaApiError(Exception):
    """IMA OpenAPI 调用错误。auth_failed=True 表示凭证问题（不可重试）。"""

    def __init__(self, msg: str, code: int = -100):
        super().__init__(msg)
        self.code = code
        self.auth_failed = (
            code in OPENAPI_AUTH_FAILED_CODES
            or code == 401
            or "auth" in str(msg).lower()
            or "401" in str(msg)
        )


class ImaOpenApiService:
    """腾讯 ima 官方 OpenAPI 客户端（v1.0.4 新增）。

    能力（官方文档 https://ima.qq.com/agent-interface）：
      - search_knowledge_base  列出/搜索账号可访问的知识库
      - get_knowledge_list      浏览知识库内容（含文件夹）
      - get_media_info          获取条目原文下载地址（url_info.url）
      - search_knowledge       知识库内全文搜索
    凭证：ima.qq.com/agent-interface → 创建凭证（ClientID + APIKey）。
    注意：凭证账号需已「加入」对应分享知识库，才能取到该库内容。
    """

    def __init__(self, client_id: str = "", api_key: str = "", throttle: float = 0.3):
        self.client_id = (client_id or "").strip()
        self.api_key = (api_key or "").strip()
        self.throttle = throttle
        self.timeout = (10, 60)
        self._lock = threading.Lock()
        self._session = requests.Session()
        self._last_call = 0.0
        self._on_log = None
        self._disabled = False
        self._disable_reason = ""
        self.kb_name = ""          # 分享库名称（KB 匹配回退用）
        self.hits = 0
        self.misses = 0
        self._direct_fail_streak = 0
        self._kb_map = None        # 回退映射: {title_lower: url}
        self._kb_map_loaded = False

    # ── 基础状态 ───────────────────────────────────────────────

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.api_key)

    @property
    def available(self) -> bool:
        return self.configured and not self._disabled

    def set_logger(self, callback):
        self._on_log = callback

    def set_share_context(self, kb_name: str):
        """告知分享库名称，直连失败超过阈值时启用 KB 匹配回退。"""
        self.kb_name = (kb_name or "").strip()

    def _log(self, msg: str):
        if self._on_log:
            self._on_log(msg)

    def _disable(self, reason: str):
        if not self._disabled:
            self._disabled = True
            self._disable_reason = reason
            self._log(f"❌ OpenAPI 已停用：{reason}（后续条目走匿名回退链）")

    # ── HTTP 调用（带节流，线程安全）────────────────────────────

    def _call(self, cmd: str, body: dict) -> dict:
        if not self.available:
            raise ImaApiError("OpenAPI 未配置或已停用")
        with self._lock:
            wait = self.throttle - (time.time() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.time()
            resp = self._session.post(
                f"{OPENAPI_BASE}/{cmd}",
                json=body,
                headers={
                    "ima-openapi-clientid": self.client_id,
                    "ima-openapi-apikey": self.api_key,
                    "Content-Type": "application/json",
                },
                timeout=self.timeout,
            )
        try:
            data = resp.json()
        except Exception:
            raise ImaApiError(f"HTTP {resp.status_code}：OpenAPI 返回非 JSON 响应", code=resp.status_code)
        code = data.get("code", resp.status_code)
        if resp.status_code == 401 or code in OPENAPI_AUTH_FAILED_CODES:
            self._disable(f"凭证无效（{code}: {data.get('msg', 'skill auth failed')}）")
            raise ImaApiError(f"{code}: {data.get('msg', 'skill auth failed')}", code=code)
        if resp.status_code >= 400 or (isinstance(code, int) and code != 0):
            raise ImaApiError(f"{code}: {data.get('msg', '')}", code=code)
        return data

    # ── 媒体地址解析（主入口）───────────────────────────────────

    def get_media_url(self, media_id: str, title: str = "") -> str:
        """解析条目下载地址。直连 get_media_info 优先，失败走 KB 匹配回退。"""
        if not self.available:
            return ""
        media_id = (media_id or "").strip()
        if not media_id and not title:
            return ""

        # 1) 直连
        if media_id:
            try:
                url = self._direct_media_url(media_id)
                if url:
                    self.hits += 1
                    self._direct_fail_streak = 0
                    return url
            except ImaApiError as e:
                if e.auth_failed:
                    return ""
                if e.code == 220030:
                    # v1.0.5.4: 官方策略——以普通成员身份加入的订阅知识库，原文对
                    # skill 整库关闭。实测（2026-11-11，新凭证下复现）同库 3/3 条目
                    # 一致 220030；而"创建者"的库正常返回下载地址。KB 匹配回退对
                    # 此类库会逐条撞同一堵墙（全库数百次无效调用），故首次命中即
                    # 停用引擎止损，本分享后续条目直接走匿名回退链。
                    self._disable(f"订阅知识库不开放 OpenAPI 原文下载（220030: {e}）")
                    return ""
            except Exception:
                pass
            self._direct_fail_streak += 1

        # 2) KB 匹配回退（直连连续失败 ≥5 或 media_id 为空）
        if self.kb_name and (title or media_id):
            if self._direct_fail_streak >= 5 or not media_id:
                url = self._lookup_in_kb_map(title, media_id)
                if url:
                    self.hits += 1
                    return url
            self.misses += 1
        return ""

    def _direct_media_url(self, media_id: str) -> str:
        data = self._call("get_media_info", {"media_id": media_id})
        return self._extract_media_url(data)

    @staticmethod
    def _extract_media_url(data) -> str:
        """从 get_media_info 响应提取下载地址。

        已知形态（ima-kb-mcp 文档）：data.url_info.url。
        防御性兼容其他变体字段，避免响应结构微调导致漏提取。
        """
        if not isinstance(data, dict):
            return ""
        d = data.get("data")
        if not isinstance(d, dict):
            d = data
        ui = d.get("url_info")
        if isinstance(ui, dict):
            u = ui.get("url")
            if isinstance(u, str) and u:
                return u
        for k in ("url", "download_url", "file_url", "media_url", "origin_url"):
            v = d.get(k)
            if isinstance(v, str) and v:
                return v
        return ""

    # ── KB 匹配回退（账号知识库枚举）────────────────────────────

    def verify(self) -> bool:
        """凭证连通性检查（GUI 启动任务时调用）。"""
        self._call("search_knowledge_base", {"query": "", "cursor": "", "limit": 1})
        return True

    def verify_detail(self) -> dict:
        """v1.0.5.1: 凭证实测（GUI「粘贴凭证」后立即调用，明示有效/无效+原因）。

        返回 {"ok": bool, "err": str, "kind": "auth"|"api"|"net"|"", "kbs": [str], "key_len": int}
          ok=True  → 凭证通过服务端鉴权（kbs 尽力列出账号可访问的知识库名）
          kind=auth → 服务端不认这对凭证（200002/401）——先查 Key 是否复制完整
                      （真实 Key 为 60+ 字符，残缺串一律 200002），再查是否被重新生成作废
          kind=net  → 网络异常（无法判定，可稍后重试）
        """
        result = {"ok": False, "err": "", "kind": "", "kbs": [],
                  "key_len": len((self.api_key or "").strip())}
        try:
            data = self._call("search_knowledge_base", {"query": "", "cursor": "", "limit": 20})
            result["ok"] = True
            names, seen = [], set()
            for d in self._iter_dicts(data):
                nm = str(d.get("name") or d.get("title") or "").strip()
                if nm and nm.lower() not in seen:
                    seen.add(nm.lower())
                    names.append(nm)
            result["kbs"] = names
        except ImaApiError as e:
            result["err"] = str(e)
            result["kind"] = "auth" if e.auth_failed else "api"
        except Exception as e:
            result["err"] = str(e)
            result["kind"] = "net"
        return result

    @staticmethod
    def _iter_dicts(obj):
        """通用 JSON 遍历：产出所有 dict（不依赖具体响应 schema）。"""
        stack = [obj]
        while stack:
            cur = stack.pop()
            if isinstance(cur, dict):
                yield cur
                stack.extend(cur.values())
            elif isinstance(cur, list):
                stack.extend(cur)

    def _lookup_in_kb_map(self, title: str, media_id: str = "") -> str:
        with self._lock:
            if self._kb_map_loaded and self._kb_map is None:
                return ""
        # 只构建一次
        with self._lock:
            if not self._kb_map_loaded:
                self._log(f"🔑 OpenAPI 直连未命中，尝试按知识库名称匹配回退：{self.kb_name}")
                self._kb_map = self._build_kb_map()
                self._kb_map_loaded = True
                if self._kb_map:
                    self._log(f"✅ KB 匹配回退已建立（{len(self._kb_map)} 个键）")
                else:
                    self._log("⚠️ KB 匹配回退未找到对应知识库/条目（账号可能未加入该库）")
        if not self._kb_map:
            return ""
        m = self._kb_map
        # 匹配优先级：media_id > 标题全等 > 标题去扩展名
        if media_id and media_id in m:
            return m[media_id]
        t = (title or "").strip().lower()
        if not t:
            return ""
        if t in m:
            return m[t]
        stem = t
        for ext in (".pdf", ".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls",
                    ".txt", ".jpg", ".jpeg", ".png", ".gif", ".webp", ".mp4",
                    ".mp3", ".zip", ".7z", ".rar", ".md"):
            if stem.endswith(ext):
                stem = stem[: -len(ext)]
                break
        if stem and stem in m:
            return m[stem]
        return ""

    def _build_kb_map(self) -> dict:
        """账号知识库 → 匹配分享库名 → 枚举条目 → {title: url}。"""
        try:
            kb_id = self._find_knowledge_base_id(self.kb_name)
            if not kb_id:
                return {}
            return self._collect_kb_media_urls(kb_id)
        except ImaApiError:
            return {}
        except Exception:
            return {}

    def _find_knowledge_base_id(self, kb_name: str) -> str:
        kb_name_l = kb_name.strip().lower()
        cursor = ""
        for _ in range(50):  # 最多翻 50 页
            data = self._call("search_knowledge_base", {"query": "", "cursor": cursor, "limit": 20})
            for d in self._iter_dicts(data):
                # v1.0.5.3: 实测响应字段为 kb_name（此前只查 name/title，永远匹配不上）
                nm = str(d.get("name") or d.get("kb_name") or d.get("title") or "").strip().lower()
                if nm and nm == kb_name_l:
                    for k in ("id", "knowledge_base_id", "kb_id"):
                        v = d.get(k)
                        if isinstance(v, str) and v:
                            return v
            nxt = ""
            for d in self._iter_dicts(data):
                v = d.get("next_cursor") or d.get("cursor")
                if isinstance(v, str) and v:
                    nxt = v
                    break
            if not nxt or nxt == cursor:
                break
            cursor = nxt
        return ""

    def _collect_kb_media_urls(self, kb_id: str) -> dict:
        """递归枚举账号知识库条目，收集 {title|media_id: url}。

        响应 schema 未知，通用遍历：含 media_id 的 dict 视为条目；
        文件夹 dict 含 folder_id + file_number。
        列表响应若直接带下载地址则零额外调用；否则逐条 get_media_info
        （账号库的 media_id 与分享库不同，直连失败后这里可能有权）。
        """
        result: dict = {}
        visited = set()
        queue = [""]  # folder_id 队列，"" 为根

        def _page_folder(folder_id: str):
            cursor = ""
            for _ in range(200):
                body = {"knowledge_base_id": kb_id, "cursor": cursor, "limit": 50}
                if folder_id:
                    body["folder_id"] = folder_id
                data = self._call("get_knowledge_list", body)
                media_dicts, folder_ids = [], []
                for d in self._iter_dicts(data):
                    mid = d.get("media_id")
                    if isinstance(mid, str) and mid:
                        media_dicts.append(d)
                        continue
                    fid = d.get("folder_id")
                    if isinstance(fid, str) and fid and "file_number" in d:
                        folder_ids.append(fid)
                for d in media_dicts:
                    mid = str(d.get("media_id") or "")
                    title = str(d.get("title") or d.get("name") or "").strip()
                    url = self._extract_media_url({"data": d})
                    if url:
                        if title:
                            result[title.lower()] = url
                        if mid:
                            result[mid] = url
                        continue
                    # 列表没带地址 → 逐条补查（节流仍在生效）
                    if mid:
                        try:
                            url2 = self._direct_media_url(mid)
                        except ImaApiError:
                            if self._disabled:
                                return folder_ids
                            url2 = ""
                        except Exception:
                            url2 = ""
                        if url2:
                            if title:
                                result[title.lower()] = url2
                            result[mid] = url2
                nxt = ""
                for d in self._iter_dicts(data):
                    v = d.get("next_cursor") or d.get("cursor")
                    if isinstance(v, str) and v:
                        nxt = v
                        break
                if not nxt or nxt == cursor:
                    return folder_ids
                cursor = nxt
            return []

        while queue:
            fid = queue.pop(0)
            if fid in visited:
                continue
            visited.add(fid)
            try:
                queue.extend(_page_folder(fid))
            except ImaApiError:
                if self._disabled:
                    break
            except Exception:
                pass

        return result

    # ── 透传接口（probe/调试用）────────────────────────────────

    def search_knowledge_base(self, query: str = "", cursor: str = "", limit: int = 20) -> dict:
        return self._call("search_knowledge_base", {"query": query, "cursor": cursor, "limit": limit})

    def get_knowledge_list(self, knowledge_base_id: str, folder_id: str = "", cursor: str = "", limit: int = 50) -> dict:
        body = {"knowledge_base_id": knowledge_base_id, "cursor": cursor, "limit": limit}
        if folder_id:
            body["folder_id"] = folder_id
        return self._call("get_knowledge_list", body)

    def search_knowledge(self, knowledge_base_id: str, query: str, cursor: str = "") -> dict:
        return self._call(
            "search_knowledge",
            {"knowledge_base_id": knowledge_base_id, "query": query, "cursor": cursor},
        )

    def get_media_info(self, media_id: str) -> dict:
        return self._call("get_media_info", {"media_id": media_id})


class ImaApiService:
    """调用 IMA 知识库分享 API"""

    def __init__(self, timeout_connect: int = 15, timeout_read: int = 180):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Content-Type": "application/json; charset=utf-8",
        })
        self.timeout_connect = timeout_connect
        self.timeout_read = timeout_read

    def get_share_info(
        self,
        share_id: str,
        limit: int = 20,
        cursor: str = "",
        folder_id: str = "",
    ) -> ShareInfoResponse:
        """
        获取分享信息（分页）
        :param share_id: 分享 ID
        :param limit: 每页数量
        :param cursor: 分页游标（首页为空字符串）
        :param folder_id: 文件夹 ID（根目录为空字符串）
        :return: ShareInfoResponse 对象
        """
        payload = ShareInfoRequest(
            share_id=share_id,
            cursor=cursor,
            limit=limit,
            folder_id=folder_id,
        )

        response = self.session.post(
            API_URL,
            json=payload.to_dict(),
            timeout=(self.timeout_connect, self.timeout_read),
        )
        response.raise_for_status()

        raw = response.json()
        return self._parse_response(raw)

    # ── 内部解析逻辑 ─────────────────────────────────────────────

    def _parse_response(self, raw: dict) -> ShareInfoResponse:
        resp = ShareInfoResponse()

        resp.code = raw.get("code", 0)
        resp.initializing = raw.get("initializing", False)
        resp.is_end = raw.get("is_end", True)
        resp.is_in_apply_list = raw.get("is_in_apply_list", False)
        resp.is_update = raw.get("is_update", False)
        resp.msg = raw.get("msg", "")
        resp.next_cursor = raw.get("next_cursor", "")
        resp.total_size = raw.get("total_size", "")
        resp.version = raw.get("version", "")

        # current_path
        for cp_data in (raw.get("current_path") or []):
            resp.current_path.append(self._parse_current_path(cp_data))

        # knowledge_list
        for item_data in (raw.get("knowledge_list") or []):
            resp.knowledge_list.append(self._parse_knowledge_item(item_data))

        # knowledge_base_info
        if raw.get("knowledge_base_info"):
            resp.knowledge_base_info = self._parse_knowledge_base_info(
                raw["knowledge_base_info"]
            )

        # version_message
        if raw.get("version_message"):
            resp.version_message = self._parse_version_message(
                raw["version_message"]
            )

        return resp

    def _parse_current_path(self, data: dict) -> CurrentPath:
        return CurrentPath(
            file_number=data.get("file_number", ""),
            folder_id=data.get("folder_id", ""),
            folder_number=data.get("folder_number", ""),
            name=data.get("name", ""),
            parent_folder_id=data.get("parent_folder_id", ""),
        )

    def _parse_folder_info(self, data: dict) -> FolderInfo:
        return FolderInfo(
            file_number=data.get("file_number", ""),
            folder_id=data.get("folder_id", ""),
            folder_number=data.get("folder_number", ""),
            name=data.get("name", ""),
            parent_folder_id=data.get("parent_folder_id", ""),
        )

    def _parse_media_type_info(self, data: dict) -> MediaTypeInfo:
        return MediaTypeInfo(
            icon=data.get("icon", ""),
            name=data.get("name", ""),
            tips=data.get("tips", ""),
        )

    def _parse_certification_info(self, data: dict) -> CertificationInfo:
        return CertificationInfo(
            company_certification_info=data.get("company_certification_info"),
            icon=data.get("icon", ""),
            personal_certification_info=data.get("personal_certification_info"),
            title=data.get("title", ""),
            type=data.get("type", 0),
            type_desc=data.get("type_desc", ""),
        )

    def _parse_creator(self, data: dict) -> Creator:
        cert_data = data.get("certification_info")
        return Creator(
            avatar_url=data.get("avatar_url", ""),
            certification_info=(
                self._parse_certification_info(cert_data)
                if cert_data else None
            ),
            knowledge_matrix_id=data.get("knowledge_matrix_id", ""),
            nickname=data.get("nickname", ""),
        )

    def _parse_knowledge_item(self, data: dict) -> KnowledgeItem:
        folder_data = data.get("folder_info")
        media_type_data = data.get("media_type_info")

        return KnowledgeItem(
            item_abstract=data.get("abstract", ""),
            access_status=data.get("access_status", 0),
            access_status_update_ts=data.get("access_status_update_ts", ""),
            cover_urls=data.get("cover_urls") or [],
            create_time=data.get("create_time", ""),
            file_size=data.get("file_size", ""),
            folder_info=self._parse_folder_info(folder_data) if folder_data else None,
            forbidden_info=data.get("forbidden_info"),
            highlight_tags=data.get("highlight_tags") or [],
            introduction=data.get("introduction", ""),
            is_repeated=data.get("is_repeated", False),
            jump_url=data.get("jump_url", ""),
            last_modify_time=data.get("last_modify_time", ""),
            last_open_time=data.get("last_open_time", ""),
            logo=data.get("logo", ""),
            md5_sum=data.get("md5_sum", ""),
            media_audit_status=data.get("media_audit_status", 0),
            media_id=data.get("media_id", ""),
            media_state=data.get("media_state", 0),
            media_type=data.get("media_type", 0),
            media_type_info=(
                self._parse_media_type_info(media_type_data)
                if media_type_data else None
            ),
            parent_folder_id=data.get("parent_folder_id", ""),
            parse_err_info=data.get("parse_err_info"),
            parse_progress=data.get("parse_progress", 0),
            parsed_file_url=data.get("parsed_file_url", ""),
            password=data.get("password", ""),
            raw_file_url=data.get("raw_file_url", ""),
            second_index=data.get("second_index", ""),
            source_path=data.get("source_path", ""),
            summary_state=data.get("summary_state", 0),
            tags=data.get("tags") or [],
            title=data.get("title", ""),
            update_time=data.get("update_time", ""),
        )

    def _parse_version_message(self, data: dict) -> VersionMessage:
        return VersionMessage(
            support_version=data.get("support_version", ""),
            tips=data.get("tips", ""),
        )

    def _parse_comment_info(self, data: dict) -> CommentInfo:
        return CommentInfo(comment_count=data.get("comment_count", ""))

    def _parse_member_info(self, data: dict) -> MemberInfo:
        return MemberInfo(
            apply_count=data.get("apply_count", 0),
            member_count=data.get("member_count", 0),
        )

    def _parse_permission_info(self, data: dict) -> PermissionInfo:
        return PermissionInfo(
            access_status=data.get("access_status", 0),
            forbid_member_access_content=data.get("forbid_member_access_content", False),
            requires_approval_for_join=data.get("requires_approval_for_join", False),
            visible_export_status=data.get("visible_export_status", 0),
        )

    def _parse_user_permission_info(self, data: dict) -> UserPermissionInfo:
        return UserPermissionInfo(
            is_in_apply_list=data.get("is_in_apply_list", False),
            role_type=data.get("role_type", 0),
        )

    def _parse_basic_info(self, data: dict) -> BasicInfo:
        creator_data = data.get("creator")
        return BasicInfo(
            cover_audit_status=data.get("cover_audit_status", 0),
            cover_url=data.get("cover_url", ""),
            create_timestamp_sec=data.get("create_timestamp_sec", ""),
            creator=self._parse_creator(creator_data) if creator_data else None,
            description=data.get("description", ""),
            forbidden_info=data.get("forbidden_info"),
            guest_cover_cos_key=data.get("guest_cover_cos_key", ""),
            has_deleted=data.get("has_deleted", False),
            knowledge_total_size=data.get("knowledge_total_size", ""),
            name=data.get("name", ""),
            recommended_questions=data.get("recommended_questions") or [],
            session_by_keyword=data.get("session_by_keyword", ""),
            size=data.get("size", ""),
            update_timestamp_sec=data.get("update_timestamp_sec", ""),
        )

    def _parse_knowledge_base_info(self, data: dict) -> KnowledgeBaseInfo:
        return KnowledgeBaseInfo(
            basic_info=self._parse_basic_info(data["basic_info"])
                if data.get("basic_info") else None,
            comment_info=self._parse_comment_info(data["comment_info"])
                if data.get("comment_info") else None,
            id=data.get("id", ""),
            member_info=self._parse_member_info(data["member_info"])
                if data.get("member_info") else None,
            permission_info=self._parse_permission_info(data["permission_info"])
                if data.get("permission_info") else None,
            type=data.get("type", 0),
            user_permission_info=self._parse_user_permission_info(
                data["user_permission_info"]
            ) if data.get("user_permission_info") else None,
        )
