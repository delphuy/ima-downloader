# models.py - 数据模型
# 对应 Java 版本中的所有 DTO helper 类

from dataclasses import dataclass, field
from typing import Optional, List
from pathlib import Path


# ── ShareInfoRequest ──────────────────────────────────────────
@dataclass
class ShareInfoRequest:
    share_id: str
    cursor: str = ""
    limit: int = 20
    folder_id: str = ""

    def to_dict(self) -> dict:
        return {
            "share_id": self.share_id,
            "cursor": self.cursor,
            "limit": self.limit,
            "folder_id": self.folder_id,
        }


# ── ShareInfoResponse ──────────────────────────────────────────
@dataclass
class ShareInfoResponse:
    code: int = 0
    current_path: List["CurrentPath"] = field(default_factory=list)
    initializing: bool = False
    is_end: bool = True
    is_in_apply_list: bool = False
    is_update: bool = False
    knowledge_base_info: Optional["KnowledgeBaseInfo"] = None
    knowledge_list: List["KnowledgeItem"] = field(default_factory=list)
    msg: str = ""
    next_cursor: str = ""
    total_size: str = ""
    version: str = ""
    version_message: Optional["VersionMessage"] = None


# ── CurrentPath ────────────────────────────────────────────────
@dataclass
class CurrentPath:
    file_number: str = ""
    folder_id: str = ""
    folder_number: str = ""
    name: str = ""
    parent_folder_id: str = ""


# ── FolderInfo ─────────────────────────────────────────────────
@dataclass
class FolderInfo:
    file_number: str = ""
    folder_id: str = ""
    folder_number: str = ""
    name: str = ""
    parent_folder_id: str = ""


# ── MediaTypeInfo ──────────────────────────────────────────────
@dataclass
class MediaTypeInfo:
    icon: str = ""
    name: str = ""
    tips: str = ""


# ── KnowledgeItem ──────────────────────────────────────────────
@dataclass
class KnowledgeItem:
    # JSON key: "abstract" (Python keyword), so rename to item_abstract
    item_abstract: str = ""
    access_status: int = 0
    access_status_update_ts: str = ""
    cover_urls: List[str] = field(default_factory=list)
    create_time: str = ""
    file_size: str = ""
    folder_info: Optional[FolderInfo] = None
    forbidden_info: Optional[dict] = None
    highlight_tags: List = field(default_factory=list)
    introduction: str = ""
    is_repeated: bool = False
    jump_url: str = ""
    last_modify_time: str = ""
    last_open_time: str = ""
    logo: str = ""
    md5_sum: str = ""
    media_audit_status: int = 0
    media_id: str = ""
    media_state: int = 0
    media_type: int = 0
    media_type_info: Optional[MediaTypeInfo] = None
    parent_folder_id: str = ""
    parse_err_info: Optional[dict] = None
    parse_progress: int = 0
    parsed_file_url: str = ""
    password: str = ""
    raw_file_url: str = ""
    second_index: str = ""
    source_path: str = ""
    summary_state: int = 0
    tags: List = field(default_factory=list)
    title: str = ""
    update_time: str = ""


# ── VersionMessage ─────────────────────────────────────────────
@dataclass
class VersionMessage:
    support_version: str = ""
    tips: str = ""


# ── Creator ────────────────────────────────────────────────────
@dataclass
class CertificationInfo:
    company_certification_info: Optional[dict] = None
    icon: str = ""
    personal_certification_info: Optional[dict] = None
    title: str = ""
    type: int = 0
    type_desc: str = ""


@dataclass
class Creator:
    avatar_url: str = ""
    certification_info: Optional[CertificationInfo] = None
    knowledge_matrix_id: str = ""
    nickname: str = ""


# ── CommentInfo ────────────────────────────────────────────────
@dataclass
class CommentInfo:
    comment_count: str = ""


# ── MemberInfo ─────────────────────────────────────────────────
@dataclass
class MemberInfo:
    apply_count: int = 0
    member_count: int = 0


# ── PermissionInfo ─────────────────────────────────────────────
@dataclass
class PermissionInfo:
    access_status: int = 0
    forbid_member_access_content: bool = False
    requires_approval_for_join: bool = False
    visible_export_status: int = 0


# ── UserPermissionInfo ─────────────────────────────────────────
@dataclass
class UserPermissionInfo:
    is_in_apply_list: bool = False
    role_type: int = 0


# ── BasicInfo ──────────────────────────────────────────────────
@dataclass
class BasicInfo:
    cover_audit_status: int = 0
    cover_url: str = ""
    create_timestamp_sec: str = ""
    creator: Optional[Creator] = None
    description: str = ""
    forbidden_info: Optional[dict] = None
    guest_cover_cos_key: str = ""
    has_deleted: bool = False
    knowledge_total_size: str = ""
    name: str = ""
    recommended_questions: List = field(default_factory=list)
    session_by_keyword: str = ""
    size: str = ""
    update_timestamp_sec: str = ""


# ── KnowledgeBaseInfo ──────────────────────────────────────────
@dataclass
class KnowledgeBaseInfo:
    basic_info: Optional[BasicInfo] = None
    comment_info: Optional[CommentInfo] = None
    id: str = ""
    member_info: Optional[MemberInfo] = None
    permission_info: Optional[PermissionInfo] = None
    type: int = 0
    user_permission_info: Optional[UserPermissionInfo] = None


# ── FailedDownload ──────────────────────────────────────────────
@dataclass
class FailedDownload:
    download_url: str
    output_path: Path

    def __str__(self):
        return f"FailedDownload(url={self.download_url}, path={self.output_path})"
