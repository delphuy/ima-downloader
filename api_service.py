# api_service.py - IMA API 服务
# 对应 Java 版本的 ImaApiService.java

import requests
from models import ShareInfoRequest, ShareInfoResponse, KnowledgeItem, CurrentPath, FolderInfo, MediaTypeInfo
from models import VersionMessage, Creator, CertificationInfo, CommentInfo, MemberInfo
from models import PermissionInfo, UserPermissionInfo, BasicInfo, KnowledgeBaseInfo


API_URL = "https://ima.qq.com/cgi-bin/knowledge_share_get/get_share_info"


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
