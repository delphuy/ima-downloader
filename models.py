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


# ── KnowledgeFile ──────────────────────────────────────────────
@dataclass
class KnowledgeFile:
    """A downloadable file with its target relative path
    (relative to the knowledge base root folder, e.g. '子目录/文件名.pdf').
    Used by unified traverser + downloader for correct folder structure.
    """
    url: str
    rel_path: Path
    title: str
    content_type: str = ""  # "链接类型", "文档类型", "文章类型" for thread grouping
    # v1.0.4: 下载来源与回退链标注
    source_kind: str = "original"
    #   "original"       官方 OpenAPI / jump_url 原件
    #   "image-original" 匿名模式图片原件（cover_urls 去 imageMogr2 压缩参数）
    #   "preview"        匿名模式 PDF/Word 首页渲染图（服务端仅签发预览）
    #   "metadata"       无任何文件地址，仅能落解析文本/摘要
    summary_text: str = ""   # 服务端 introduction 开头摘录（实测约200-300字，非全文）
    abstract_text: str = ""  # AI 摘要(abstract)，用于 _摘要.txt
    media_id: str = ""       # 官方 OpenAPI get_media_info 所需
    file_size: str = ""     # 原件大小（服务端上报，用于统计核对）
    md5_sum: str = ""       # 服务端上报 md5（实测为 COS ETag，非文件字节 md5，仅记录不作校验依据）
    raw_file_url: str = ""  # v1.0.7: 服务端对象路径（如 5/<bucket>/file_manager/<hash>.pdf），
                            #   客户端收割通道的备用匹配键


# ── DownloadReport ─────────────────────────────────────────────
@dataclass
class DownloadReport:
    """v1.0.4: 下载结果统计，供 GUI 三态诚实汇报。"""
    failed: List[FailedDownload] = field(default_factory=list)
    original: int = 0         # 原件成功（OpenAPI / jump_url）
    image_original: int = 0   # 匿名模式图片原件成功
    preview: int = 0           # 匿名模式首页预览图成功
    text_only: int = 0        # 无文件地址、仅落解析文本/摘要
    skipped: int = 0           # 已存在跳过
    # v1.0.6: 逐文件字节校验（用户要求"下载完必须自测比对"）
    size_pass: int = 0         # 原件/图片原件 实际字节数 == 服务端 file_size
    size_fail: int = 0         # 字节数不符（下载不完整/损坏铁证）
    preview_ok: int = 0        # 预览图存在且为合法 JPEG
    preview_bad: int = 0       # 预览图缺失/非 JPEG
    verify_rows: List[tuple] = field(default_factory=list)
    #   每行 = (排序优先级, 相对路径, 报告行文本)；优先级 0=异常 1=预览 2=通过 3=跳过/无地址
    verify_base_dir: str = ""  # 由下载层回填，校验报告写到这里
    # v1.0.7: 客户端签名原件收割（内容级核对通道）
    harvest_attempted: bool = False   # 收割阶段是否实际运行
    harvest_client_found: bool = False  # 是否找到本机 ima 客户端数据目录
    harvest_matched: int = 0     # 本地客户端库中找到签名的条目数
    harvest_ok: int = 0         # 收割成功（字节级核验通过；已在本地复核的也计入）
    harvest_fail: int = 0        # 收割失败（签名过期 403 / 字节不符 / IO）
    harvest_unmatched: int = 0   # 需要原件但本地客户端无签名的文档数
    harvest_pages: int = 0       # 收割原件 PDF 合计页数（pypdf 精确/近似标注见逐行）

    @property
    def downloaded(self) -> int:
        return self.original + self.image_original + self.preview

    @property
    def total(self) -> int:
        return self.downloaded + self.text_only + self.skipped + len(self.failed)

    def summary_line(self) -> str:
        return (
            f"原件 {self.original} · 图片原件 {self.image_original} · "
            f"首页预览 {self.preview} · 仅文本 {self.text_only} · "
            f"已存在 {self.skipped} · 失败 {len(self.failed)}"
        )

    def verify_summary_line(self) -> str:
        """v1.0.6: 校验摘要（跟在 summary_line 后展示）。"""
        return (
            f"字节校验通过 {self.size_pass} · 字节不符 {self.size_fail} · "
            f"预览校验通过 {self.preview_ok} · 预览异常 {self.preview_bad}"
        )

    def harvest_summary_line(self) -> str:
        """v1.0.7: 收割摘要（收割阶段运行过才有意义）。"""
        return (f"收割原件 成功 {self.harvest_ok} · PDF 合计 {self.harvest_pages} 页 · "
                f"失败 {self.harvest_fail} · 未匹配 {self.harvest_unmatched}")

    def content_coverage_lines(self) -> List[str]:
        """v1.0.7: 内容覆盖统计 —— 回答「文件数对了，内容数对了吗」。

        - 原件/图片原件：字节级 == 服务端 file_size → 内容完整可信；
        - 收割原件：客户端签名通道取得的完整原件，PDF 逐份计页；
        - 首页预览：每份只有第 1 页，明确声明不等于完整文档
          （服务端匿名面无页数字段、多页签名逐对象锁定，均为实测边界）。
        """
        lines = ["内容覆盖统计（v1.0.7 内容级核对）:"]
        if self.harvest_attempted:
            if not self.harvest_client_found:
                lines.append("  收割通道: 未找到本机 ima 客户端数据目录，未执行收割")
            else:
                lines.append(
                    f"  收割原件: {self.harvest_ok} 份 · 字节级核验通过 · "
                    f"PDF 合计 {self.harvest_pages} 页"
                    + (f"（另有 {self.harvest_fail} 份失败：签名过期/字节不符，见 🌾/❌ 行）"
                       if self.harvest_fail else ""))
        if self.preview_ok or self.preview_bad:
            lines.append(
                f"  首页预览: {self.preview_ok} 份 — 每份仅含第 1 页，不等于完整文档"
                f"（服务端匿名面不签发原件地址，也无页数字段）")
        lines.append(
            f"  原件字节级通过: {self.size_pass} 份 — 实际字节数 == 服务端 file_size"
            f"（含图片原件与收割原件；字节一致即内容完整）")
        if self.harvest_attempted and self.harvest_client_found and self.harvest_unmatched:
            lines.append(
                f"  未收割文档: {self.harvest_unmatched} 份 — 本机 ima 客户端未打开过，"
                f"暂无原件签名（在客户端打开一次后重新运行下载即可收割）")
        return lines

    def write_verify_report(self, base_dir=None) -> Optional[Path]:
        """v1.0.6: 写出逐文件校验报告 下载校验报告.txt，返回报告路径。

        base_dir 显式传入优先，否则用下载层回填的 verify_base_dir。
        无任何校验行时返回 None（不产出空报告）。
        """
        if not self.verify_rows:
            return None
        root = None
        if base_dir is not None:
            root = Path(base_dir)
        elif self.verify_base_dir:
            root = Path(self.verify_base_dir)
        if root is None:
            return None
        root.mkdir(parents=True, exist_ok=True)
        out = root / "下载校验报告.txt"
        from datetime import datetime
        header = [
            "IMA 下载校验报告（v1.0.7 逐文件自测比对 + 内容级核对，自动生成）",
            f"生成时间: {datetime.now():%Y-%m-%d %H:%M:%S}",
            "",
            f"统计: {self.verify_summary_line()} · 下载失败 {len(self.failed)} · "
            f"仅文本 {self.text_only} · 已存在跳过 {self.skipped}",
            "图例: ✅=实际字节数与服务端上报完全一致 · 🔍=首页预览图（非原件）"
            " · 🌾=客户端签名通道收割的完整原件（含页数核对）"
            " · ❌=异常需处理 · ⏭=已存在未重下（就地校验） · ⏸=服务端无文件地址",
            "=" * 72,
        ]
        if self.harvest_attempted:
            header.insert(3, f"收割: {self.harvest_summary_line()}")
        header.append("")
        header.extend(self.content_coverage_lines())
        header.append("=" * 72)
        rows = [line for _, _, line in sorted(self.verify_rows, key=lambda t: (t[0], t[1]))]
        out.write_text("\n".join(header + rows) + "\n", encoding="utf-8")
        return out
